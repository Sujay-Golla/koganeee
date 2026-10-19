"""Capture a stationary measured checkerboard in both cameras and calibrate stereo."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time
import uuid

import numpy as np

from .stereo import PairSelector, StereoCalibration, StereoError

BASE = Path(__file__).resolve().parents[2]


def board_html():
    # 10x7 squares -> 9x6 INNER corners. Tablet pixels do not determine physical size.
    squares = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="black"/>'
                      for y in range(7) for x in range(10) if (x+y)%2 == 0)
    return f'''<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kogane stereo checkerboard</title><style>
body{{margin:0;background:white;font-family:system-ui;text-align:center;overflow:hidden}}
#board{{display:block;width:min(90vw,125vh);height:auto;margin:2vh auto}}
button{{font-size:18px;padding:8px}}p{{margin:4px;font-size:14px}}
:fullscreen #controls{{display:none}}:fullscreen #board{{margin:4vh auto}}
</style><div id="controls"><p>9 x 6 INNER corners. Measure one square AFTER fullscreen.
Keep tablet orientation, zoom and brightness fixed.</p>
<button onclick="document.documentElement.requestFullscreen?.()">Fullscreen pattern</button></div>
<svg id="board" xmlns="http://www.w3.org/2000/svg" viewBox="-0.5 -0.5 11 8">
<rect x="-0.5" y="-0.5" width="11" height="8" fill="white"/>{squares}</svg>
<script>navigator.wakeLock?.request('screen').catch(()=>{{}});</script></html>'''


def serve_board(port):
    page = board_html().encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/", "/board"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *args):
            pass

    print(f"Tablet on same Wi-Fi: http://LAPTOP_WIFI_IP:{port}/", flush=True)
    print("Only the generated checkerboard is served; no project files. Ctrl+C stops.", flush=True)
    with HTTPServer(("0.0.0.0", port), Handler) as server:
        server.serve_forever()


def object_points(square_m, pattern=(9, 6)):
    points = np.zeros((pattern[0]*pattern[1], 3), np.float32)
    points[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2)*square_m
    return points


def fit_observations(objects, left, right, size):
    import cv2
    flags = cv2.CALIB_FIX_K3
    rms1, k1, d1, *_ = cv2.calibrateCamera(objects, left, size, None, None, flags=flags)
    rms2, k2, d2, *_ = cv2.calibrateCamera(objects, right, size, None, None, flags=flags)
    result = cv2.stereoCalibrate(objects, left, right, k1, d1, k2, d2, size,
                                 flags=cv2.CALIB_FIX_INTRINSIC,
                                 criteria=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6))
    return result, (rms1, rms2)


def vertical_errors(result, left, right, size):
    import cv2
    _, k1, d1, k2, d2, rotation, translation, *_ = result
    r1, r2, p1, p2, *_ = cv2.stereoRectify(k1, d1, k2, d2, size, rotation, translation,
                                          flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)
    errors = []
    for a, b in zip(left, right):
        a = cv2.undistortPoints(a, k1, d1, R=r1, P=p1).reshape(-1, 2)
        b = cv2.undistortPoints(b, k2, d2, R=r2, P=p2).reshape(-1, 2)
        errors.extend(abs(a[:, 1]-b[:, 1]))
    return np.asarray(errors), p1, p2


def solve(samples, *, size, devices, square_m, expected_baseline,
          allow_limited_coverage=False, report=None):
    import cv2
    if len(samples) < 18:
        raise StereoError("Capture at least 18 different stationary board poses before solving.")
    if not .002 <= square_m <= .10:
        raise StereoError("Square size must be a measured 2–100 mm, entered in metres internally.")
    objects = [object_points(square_m) for _ in samples]
    left = [np.asarray(pair[0], np.float32).reshape(-1, 1, 2) for pair in samples]
    right = [np.asarray(pair[1], np.float32).reshape(-1, 1, 2) for pair in samples]
    if any(points.shape != (54, 1, 2) or not np.isfinite(points).all() for points in left+right):
        raise StereoError("Each checkerboard view needs 54 finite inner corners.")
    coverage, limited = [], []
    for index, observations in enumerate((left, right)):
        centres = np.array([p.reshape(-1, 2).mean(axis=0) for p in observations])
        areas = np.array([np.ptp(p[:, 0, 0])*np.ptp(p[:, 0, 1]) for p in observations])
        span = np.ptp(centres, axis=0)
        ratio = float(max(areas)/max(1, min(areas)))
        coverage.append(dict(device=devices[index], centre_span_px=span.tolist(), size_ratio=ratio))
        if span[0] < size[0]*.12 or span[1] < size[1]*.10 or ratio < 1.4:
            limited.append(f"Device {devices[index]}: limited board coverage (span {span[0]:.1f}x{span[1]:.1f}px, size ratio {ratio:.2f}).")
    if limited and not allow_limited_coverage:
        raise StereoError("Board poses lack coverage/size variation. Saved corners can be evaluated with --solve-only --allow-limited-coverage; geometric quality checks still apply.")
    result, (rms1, rms2) = fit_observations(objects, left, right, size)
    rms, k1, d1, k2, d2, rotation, translation, *_ = result
    errors, p1, p2 = vertical_errors(result, left, right, size)
    epipolar = float(np.median(errors))
    if max(rms1, rms2) > 1.5 or np.percentile(errors, 95) > 2:
        raise StereoError(f"Calibration quality too low: individual RMS {rms1:.2f}/{rms2:.2f}px, vertical p95 {np.percentile(errors,95):.2f}px. Recapture sharper stationary poses.")
    calibration = StereoCalibration(k1, d1, k2, d2, rotation, translation, size, devices, float(rms), epipolar)
    calibration.validate_capture(devices, size, expected_baseline)
    if p2[0, 3] >= 0 or abs(p2[1, 3]) > abs(p2[0, 3])*.1:
        raise StereoError("Camera order/baseline is wrong for horizontal stereo. Check physical left/right order.")
    held_out = []
    if limited:
        for fold in range(3):
            train = [i for i in range(len(samples)) if i % 3 != fold]
            test = [i for i in range(len(samples)) if i % 3 == fold]
            fitted, individual = fit_observations([objects[i] for i in train], [left[i] for i in train],
                                                  [right[i] for i in train], size)
            err, fp1, fp2 = vertical_errors(fitted, [left[i] for i in test], [right[i] for i in test], size)
            baseline = float(np.linalg.norm(fitted[6]))
            median, p95 = float(np.median(err)), float(np.percentile(err, 95))
            if max(individual) > 1.5 or median > 1 or p95 > 2 or abs(baseline-expected_baseline) > max(.02, .15*expected_baseline):
                raise StereoError(f"Limited-coverage calibration failed held-out fold {fold+1}: baseline {baseline:.3f}m, vertical median {median:.2f}px/p95 {p95:.2f}px. More diverse captures are needed.")
            held_out.append(dict(fold=fold+1, baseline_m=baseline, focal_px=float(fp1[0, 0]),
                                 median_vertical_px=median, p95_vertical_px=p95))
        baselines = [r["baseline_m"] for r in held_out]
        focals = [r["focal_px"] for r in held_out]
        if np.ptp(baselines)/calibration.baseline_m > .10 or np.ptp(focals)/p1[0, 0] > .25:
            raise StereoError("Limited captures give unstable calibration between held-out folds; more diverse poses are required.")
        calibration.quality_notes = limited + [
            "Limited-coverage demo calibration passed 3 held-out folds. Verify distances against a ruler/tape before trusting room position."]
    if report is not None:
        report.update(pairs=len(samples), devices=devices, square_m=square_m, coverage=coverage,
                      rms_px=float(rms), median_vertical_px=epipolar,
                      p95_vertical_px=float(np.percentile(errors, 95)),
                      baseline_m=calibration.baseline_m, rectified_focal_px=float(p1[0, 0]),
                      held_out=held_out, quality_notes=calibration.quality_notes)
    return calibration


def corner_array(corners):
    """Normalize OpenCV's Nx2 and Nx1x2 point outputs at the detector boundary."""
    points = np.asarray(corners, dtype=np.float32)
    if points.shape not in ((54, 2), (54, 1, 2)) or not np.isfinite(points).all():
        raise StereoError(f"Unexpected checkerboard corner array: {points.shape}; expected 54 image points.")
    return np.ascontiguousarray(points.reshape(54, 1, 2))


def detect_board(image):
    import cv2
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ok, corners = cv2.findChessboardCornersSB(gray, (9, 6), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    return corner_array(corners) if ok else None


def draw_board(image, corners):
    import cv2
    points = corner_array(corners)
    cv2.drawChessboardCorners(image, (9, 6), points, True)
    origin = tuple(int(round(float(value))) for value in points[0, 0])
    cv2.putText(image, "0", origin, cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)


def save_result(calibration, out, report_path, report):
    calibration.save(out)
    save_json(report_path, report)
    print(f"PASS: saved {out.resolve()}\nBaseline={calibration.baseline_m:.3f}m RMS={calibration.rms_px:.2f}px median vertical={calibration.epipolar_px:.2f}px", flush=True)
    for note in calibration.quality_notes:
        print(f"NOTE: {note}", flush=True)
    print(f"Quality report: {report_path.resolve()}", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--serve-board", action="store_true")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--make-board", type=Path)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--camera2", type=int, default=1)
    p.add_argument("--square-mm", type=float, help="MEASURED width of one displayed square in millimetres")
    p.add_argument("--baseline", type=float, default=.40)
    p.add_argument("--capture-width", type=int, default=640)
    p.add_argument("--capture-height", type=int, default=480)
    p.add_argument("--capture-fps", type=float, default=15)
    p.add_argument("--camera-api", choices=["auto", "dshow", "msmf"], default="auto")
    p.add_argument("--out", type=Path, default=BASE / "calib" / "stereo.json")
    p.add_argument("--samples", type=Path, default=BASE / "outputs" / "stereo_samples.json")
    p.add_argument("--image-dir", type=Path, default=BASE / "outputs" / "stereo_capture")
    p.add_argument("--report", type=Path, default=BASE / "outputs" / "stereo_calibration_report.json")
    p.add_argument("--allow-limited-coverage", action="store_true",
                   help="evaluate limited coverage with additional held-out checks; does not relax geometric quality limits")
    p.add_argument("--solve-only", action="store_true", help="retry solving previously captured corner pairs")
    args = p.parse_args(argv)
    if args.make_board:
        args.make_board.parent.mkdir(parents=True, exist_ok=True)
        args.make_board.write_text(board_html(), encoding="utf-8")
        print(args.make_board.resolve())
        return 0
    if args.serve_board:
        serve_board(args.port)
        return 0
    if args.square_mm is None or not 2 <= args.square_mm <= 100:
        p.error("--square-mm must be the measured width (2–100 mm) of one square at the tablet's fixed fullscreen size.")
    if args.camera == args.camera2:
        p.error("Choose two different camera indices in physical left/right order.")
    if args.solve_only:
        data = json.loads(args.samples.read_text(encoding="utf-8"))
        if tuple(data["devices"]) != (args.camera, args.camera2) or abs(data["square_mm"]-args.square_mm) > .001:
            raise StereoError("Saved sample device order/square size differs from this command.")
        report = {}
        cal = solve(data["samples"], size=tuple(data["size"]), devices=(args.camera, args.camera2),
                    square_m=args.square_mm/1000, expected_baseline=args.baseline,
                    allow_limited_coverage=args.allow_limited_coverage, report=report)
        save_result(cal, args.out, args.report, report)
        return 0

    import cv2
    from ..tools.mapping_multi import LatestCamera
    readers = []
    samples, size, seen = [], None, None
    selector = PairSelector()
    current = None
    image_pairs = []
    capture_dir = args.image_dir / (time.strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    message = "Hold tablet still. S capture | Enter solve (18+ poses) | Q quit"
    try:
        for index in (args.camera, args.camera2):
            reader = LatestCamera(index, width=args.capture_width, height=args.capture_height,
                                  fps=args.capture_fps, api=args.camera_api)
            readers.append(reader)
            reader.start()
        start = time.monotonic()
        canvas = np.full((570, 1280, 3), 20, np.uint8)
        while True:
            histories = [r.history() for r in readers]
            pair = selector.select(*(h[0] for h in histories), now=time.monotonic())
            if pair:
                if pair[0].image.shape != pair[1].image.shape:
                    raise StereoError("Stereo calibration requires equal image dimensions on both cameras.")
                size = (pair[0].image.shape[1], pair[0].image.shape[0])
                images = [f.image.copy() for f in pair]
                corners = [detect_board(img) for img in images]
                if all(c is not None for c in corners):
                    # Normalize a possible 180-degree ordering flip between similar views.
                    da, db = (c[8, 0]-c[0, 0] for c in corners)
                    if np.dot(da, db) < 0:
                        corners[1] = corners[1][::-1].copy()
                    current = (corners, min(f.t_mono for f in pair), [f.image.copy() for f in pair])
                else:
                    current = None
                canvas[:] = 20
                for i, (image, pts) in enumerate(zip(images, corners)):
                    if pts is not None:
                        draw_board(image, pts)
                    image = cv2.resize(image, (640, 480))
                    canvas[40:520, i*640:(i+1)*640] = image
                    cv2.putText(canvas, f"{'LEFT' if i == 0 else 'RIGHT'} / DEVICE {(args.camera,args.camera2)[i]} / {'BOARD FOUND' if pts is not None else 'FINDING 9x6 INNER CORNERS'}",
                                (i*640+10, 27), cv2.FONT_HERSHEY_SIMPLEX, .5, (100, 230, 220), 1)
                seen = pair
            cv2.rectangle(canvas, (0, 522), (1280, 570), (20, 20, 20), -1)
            cv2.putText(canvas, f"{len(samples)} PAIRS | {message}"[:150], (12, 552), cv2.FONT_HERSHEY_SIMPLEX, .48, (220, 220, 220), 1)
            cv2.imshow("Kogane stereo calibration - S capture, Enter solve, Q quit", canvas)
            key = cv2.waitKey(10) & 0xff
            if key == ord("q"):
                return 0
            if key == ord("s"):
                if current is None or time.monotonic()-current[1] > .8:
                    message = "Need a fresh board detection in BOTH cameras. Hold it still and try S again."
                elif samples and max(np.mean(np.linalg.norm(current[0][i]-np.array(samples[-1][i]), axis=2)) for i in (0, 1)) < 12:
                    message = "Move/tilt tablet to a different pose before another capture."
                else:
                    samples.append([c.tolist() for c in current[0]])
                    capture_dir.mkdir(parents=True, exist_ok=True)
                    paths = []
                    for side, image in zip(("left", "right"), current[2]):
                        path = capture_dir / f"pair_{len(samples):03d}_{side}.png"
                        try:
                            written = cv2.imwrite(str(path), image)
                        except (cv2.error, OSError):
                            written = False
                        paths.append(str(path) if written else None)
                        if not written:
                            print(f"Could not save image {path}; corner coordinates will still be saved.", flush=True)
                    image_pairs.append(paths)
                    save_json(args.samples, dict(size=size, devices=[args.camera, args.camera2],
                                                 square_mm=args.square_mm, samples=samples, image_pairs=image_pairs))
                    message = "Saved. Move near/far, high/low, left/right, and tilt; hold still, then S."
            if key in (10, 13):
                try:
                    message = "SOLVING..."
                    cv2.putText(canvas, message, (12, 535), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 1)
                    cv2.imshow("Kogane stereo calibration - S capture, Enter solve, Q quit", canvas)
                    cv2.waitKey(1)
                    report = {}
                    cal = solve(samples, size=size, devices=(args.camera, args.camera2), square_m=args.square_mm/1000,
                                expected_baseline=args.baseline, allow_limited_coverage=args.allow_limited_coverage,
                                report=report)
                    save_result(cal, args.out, args.report, report)
                    return 0
                except (StereoError, cv2.error) as exc:
                    message = str(exc)
                    print(f"Calibration not accepted: {exc}", flush=True)
            if seen is None and time.monotonic()-start > 20:
                raise StereoError(f"No fresh camera pairs. Camera statuses: {[h[1] for h in histories]}. Close other camera apps; verify indices and USB ports.")
    finally:
        for reader in readers:
            reader.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (StereoError, OSError) as exc:
        print(f"Stereo calibration stopped: {exc}")
        raise SystemExit(1)
