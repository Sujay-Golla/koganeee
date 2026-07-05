"""Standalone CV test: person detection + tracking on a webcam (or video/MJPEG).

Examples
--------
    kogane-cv                                   # webcam 0, live window
    python -m kogane_base.vision.demo --source webcam --camera 0
    python -m kogane_base.vision.demo --source video --path clip.mp4
    python -m kogane_base.vision.demo --source mjpeg --url http://192.168.4.2/stream
    python -m kogane_base.vision.demo --fuse     # also run the Kalman filter on the target
    python -m kogane_base.vision.demo --headless # no window (prints target position)

Keys in the window:  q = quit   l = lock/unlock onto the current primary target

This needs the vision extra:  pip install -e .[vision]
Nothing about it requires the drone — it runs entirely on the laptop.
"""
from __future__ import annotations

import argparse
import sys
import time


def _fail_missing(dep: str, exc: Exception) -> "None":
    print(f"[kogane-cv] missing dependency '{dep}': {exc}\n"
          f"install the vision extra:  pip install -e .[vision]", file=sys.stderr)
    raise SystemExit(2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kogane person-tracking CV test")
    p.add_argument("--source", choices=["webcam", "video", "mjpeg", "usb"], default="webcam")
    p.add_argument("--camera", type=int, default=0, help="webcam/usb index")
    p.add_argument("--path", help="video file path (--source video)")
    p.add_argument("--url", help="MJPEG stream URL (--source mjpeg)")
    p.add_argument("--model", default="yolov8n.pt", help="ultralytics model (auto-downloads)")
    p.add_argument("--device", default="cpu", help="cpu | 0 (cuda:0) | mps")
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--hfov", type=float, default=70.0, help="camera horizontal FOV deg")
    p.add_argument("--person-height", type=float, default=1.7, help="assumed person height m")
    p.add_argument("--fuse", action="store_true", help="run the Kalman filter on the target")
    p.add_argument("--headless", action="store_true", help="no display window")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    try:
        import cv2  # noqa: F401
    except Exception as e:  # pragma: no cover
        _fail_missing("opencv-python", e)
    try:
        from .detector import PersonDetector, select_primary
    except Exception as e:  # pragma: no cover
        _fail_missing("ultralytics", e)

    from .geometry import MonocularEstimator
    from .sources import make_source

    value = {"webcam": str(args.camera), "usb": str(args.camera),
             "video": args.path, "mjpeg": args.url}[args.source]

    print(f"[kogane-cv] opening source={args.source} value={value!r}")
    src = make_source(args.source, value)
    w, h = src.size
    if w == 0 or h == 0:
        # some webcams report 0 until the first frame; peek one frame
        first = next(iter(src))
        h, w = first.image.shape[:2]
        frames = _chain_first(first, src)
    else:
        frames = iter(src)

    print(f"[kogane-cv] frame size {w}x{h}; loading model {args.model} on {args.device} ...")
    detector = PersonDetector(args.model, device=args.device, conf=args.conf)
    estimator = MonocularEstimator(w, h, hfov_deg=args.hfov,
                                   assumed_person_height_m=args.person_height)

    kf = None
    if args.fuse:
        from ..fusion.kalman import PositionFilter
        kf = PositionFilter()

    locked_id: int | None = None
    ema_fps = 0.0
    last = time.monotonic()

    try:
        for frame in frames:
            tracks = detector.track(frame.image)
            primary = select_primary(tracks, locked_id)

            now = time.monotonic()
            dt = max(1e-3, now - last)
            last = now
            ema_fps = 0.9 * ema_fps + 0.1 * (1.0 / dt) if ema_fps else 1.0 / dt

            target_txt = "no target"
            if primary is not None:
                fx, fy = primary.foot
                est = estimator.estimate(primary.x1, primary.y1, primary.x2, primary.y2,
                                         primary.conf)
                if kf is not None:
                    kf.predict(dt)
                    kf.update(est.x_m, est.y_m)
                    px, py = kf.position
                    target_txt = (f"id={primary.track_id} bearing={est.bearing_deg:+.0f} "
                                  f"dist~{est.distance_m:.1f}m  KF=({px:+.2f},{py:+.2f})")
                else:
                    target_txt = (f"id={primary.track_id} bearing={est.bearing_deg:+.0f} "
                                  f"dist~{est.distance_m:.1f}m  cam=({est.x_m:+.2f},{est.y_m:+.2f})")

            if args.headless:
                if frame.index % 15 == 0:
                    print(f"[{ema_fps:4.1f} fps] {target_txt}")
            else:
                _draw(cv2, frame.image, tracks, primary, ema_fps, target_txt, locked_id)
                cv2.imshow("kogane-cv (q quit, l lock)", frame.image)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("l"):
                    locked_id = None if locked_id is not None else (
                        primary.track_id if primary else None)
                    print(f"[kogane-cv] locked_id -> {locked_id}")
    finally:
        src.release()
        if not args.headless:
            import cv2 as _cv2
            _cv2.destroyAllWindows()


def _chain_first(first, src):
    yield first
    yield from src


def _draw(cv2, img, tracks, primary, fps, target_txt, locked_id) -> None:
    for t in tracks:
        is_primary = primary is not None and t is primary
        color = (0, 0, 255) if is_primary else (0, 200, 0)
        thick = 3 if is_primary else 1
        cv2.rectangle(img, (int(t.x1), int(t.y1)), (int(t.x2), int(t.y2)), color, thick)
        tag = f"#{t.track_id}"
        if is_primary:
            tag += " *LOCK*" if locked_id is not None else " *primary*"
        cv2.putText(img, tag, (int(t.x1), int(t.y1) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(img, f"{fps:4.1f} fps", (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    cv2.putText(img, target_txt, (8, img.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)


if __name__ == "__main__":
    main()
