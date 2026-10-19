"""Live webcam/person map, optional real LD2450, and local MP4 recording.

Standalone observer: no drone sockets, setpoints, arming or flight commands.
The plot maps detected people, not reconstructed walls or a 3D SLAM map.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import threading
import time

import numpy as np

from ..fusion.kalman import PositionFilter

BASE = Path(__file__).resolve().parents[2]
BG = (21, 18, 15)
CARD = (32, 28, 23)
INK = (235, 237, 239)
MUTED = (155, 155, 150)
CYAN = (222, 214, 65)
AMBER = (64, 181, 255)
GREEN = (145, 223, 100)
PURPLE = (233, 137, 191)


@dataclass
class TargetState:
    stale_s: float = 0.8
    xy: tuple[float, float] | None = None
    track_id: int | None = None
    updated: float = -math.inf
    trail: deque = field(default_factory=lambda: deque(maxlen=240))
    kf: PositionFilter = field(default_factory=PositionFilter)

    def observe(self, x: float, y: float, track_id: int, timestamp: float) -> bool:
        if not all(math.isfinite(v) for v in (x, y, timestamp)):
            return False
        if timestamp < self.updated:
            return False
        if track_id != self.track_id or timestamp - self.updated > self.stale_s:
            self.kf = PositionFilter()
            self.trail.clear()
        else:
            self.kf.predict(min(timestamp - self.updated, self.stale_s))
        self.kf.update(x, y)
        self.xy = self.kf.position
        self.track_id = track_id
        self.updated = timestamp
        self.trail.append(self.xy)
        return True

    def fresh(self, now: float) -> bool:
        return self.xy is not None and 0 <= now - self.updated <= self.stale_s

    def clear(self) -> None:
        self.xy = None
        self.updated = -math.inf
        self.track_id = None
        self.kf = PositionFilter()
        self.trail.clear()


class RadarFeed:
    """Read-only serial reports. Reports replace previous targets, including empty ones."""

    def __init__(self, port: str, pose: tuple[float, float, float]) -> None:
        self.port, self.pose = port, pose
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.points: list[tuple[float, float]] = []
        self.updated = -math.inf
        self.frames = 0
        self.error = "opening"
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def snapshot(self, now: float):
        with self.lock:
            points = list(self.points) if 0 <= now - self.updated <= 0.8 else []
            return points, self.frames, self.error, now - self.updated

    def _run(self) -> None:
        from ..tracking.ld2450 import Ld2450Parser
        try:
            import serial
            parser = Ld2450Parser()
            ox, oy, yaw = self.pose
            a = math.radians(yaw)
            with serial.Serial(self.port, 256000, timeout=0.15) as stream:
                with self.lock:
                    self.error = "waiting for reports"
                while not self.stop_event.is_set():
                    for targets in parser.feed(stream.read(64)):
                        points = []
                        for target in targets:
                            x, y = target.x_mm / 1000, target.y_mm / 1000
                            points.append((ox + x * math.cos(a) - y * math.sin(a),
                                           oy + x * math.sin(a) + y * math.cos(a)))
                        with self.lock:
                            self.points = points
                            self.updated = time.monotonic()
                            self.frames += 1
                            self.error = ""
        except Exception as exc:
            with self.lock:
                self.points = []
                self.error = str(exc)
            print(f"Radar unavailable: {exc}", flush=True)

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1.0)


def label(img, text, x, y, size=0.55, color=INK, thick=1):
    import cv2
    cv2.putText(img, str(text), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                size, color, thick, cv2.LINE_AA)


def plot_point(xy, room, bounds):
    x, y = xy
    w, h = room
    left, top, right, bottom = bounds
    if not all(math.isfinite(v) for v in (x, y)) or not (0 <= x <= w and 0 <= y <= h):
        return None
    return round(left + x / w * (right - left)), round(bottom - y / h * (bottom - top))


def render_overlay(image, tracks, target: TargetState, *, now: float,
                   room=(4.0, 5.0), camera_pose=(2.0, 0.0, 0.0), fps=0.0,
                   calibrated=False, radar_points=(), radar_status="NOT CONNECTED",
                   recording=False, preview=False):
    import cv2
    out = np.full((720, 1280, 3), BG, np.uint8)
    label(out, "KOGANE", 28, 49, 1.18, INK, 2)
    label(out, "ROOM TRACKING", 228, 48, 0.63, CYAN, 2)
    label(out, "LAYOUT PREVIEW / NOT LIVE" if preview else "LIVE SENSOR VIEW",
          870, 43, 0.57, AMBER if preview else GREEN, 1)
    if recording:
        cv2.circle(out, (1228, 37), 6, (65, 65, 245), -1)
    label(out, "CAMERA / PERSON DETECTION", 28, 91, 0.5, MUTED)
    label(out, "TOP-DOWN POSITION MAP", 830, 91, 0.5, MUTED)

    frame = image.copy()
    for track in tracks:
        color = CYAN if track.track_id == target.track_id else MUTED
        p1, p2 = (int(track.x1), int(track.y1)), (int(track.x2), int(track.y2))
        cv2.rectangle(frame, p1, p2, color, 2)
        label(frame, f"PERSON {track.track_id} / {track.conf:.0%}", p1[0],
              max(22, p1[1] - 8), 0.56, color, 2)
        cv2.circle(frame, tuple(map(int, track.foot)), 5, color, -1)
    x0, y0, cw, ch = 28, 112, 770, 452
    cv2.rectangle(out, (x0, y0), (x0 + cw, y0 + ch), CARD, -1)
    ih, iw = frame.shape[:2]
    scale = min(cw / iw, ch / ih)
    rw, rh = max(1, round(iw * scale)), max(1, round(ih * scale))
    resized = cv2.resize(frame, (rw, rh))
    px, py = x0 + (cw - rw) // 2, y0 + (ch - rh) // 2
    out[py:py + rh, px:px + rw] = resized

    cv2.rectangle(out, (826, 112), (1252, 564), CARD, -1)
    w, h = room
    m = min(330 / w, 335 / h)
    pw, ph = round(w * m), round(h * m)
    left, top = 1039 - pw // 2, 170
    bounds = (left, top, left + pw, top + ph)
    label(out, f"{w:g} m x {h:g} m reference area", 850, 143, 0.49, MUTED)
    for gx in np.arange(0, w + 0.001, 1.0):
        p = plot_point((float(gx), 0), room, bounds)
        if p:
            cv2.line(out, (p[0], top), (p[0], top + ph), (65, 58, 47), 1)
    for gy in np.arange(0, h + 0.001, 1.0):
        p = plot_point((0, float(gy)), room, bounds)
        if p:
            cv2.line(out, (left, p[1]), (left + pw, p[1]), (65, 58, 47), 1)
    cv2.rectangle(out, (left, top), (left + pw, top + ph), MUTED, 1)
    for a, b in zip(target.trail, list(target.trail)[1:]):
        pa, pb = plot_point(a, room, bounds), plot_point(b, room, bounds)
        if pa is not None and pb is not None:
            cv2.line(out, pa, pb, (122, 119, 55), 2, cv2.LINE_AA)
    cam = plot_point(camera_pose[:2], room, bounds)
    if cam:
        cv2.drawMarker(out, cam, INK, cv2.MARKER_TRIANGLE_UP, 14, 2)
        label(out, "CAMERA / WALL", left + 15, top + ph + 28, 0.43, MUTED)
    live = target.fresh(now)
    if live:
        p = plot_point(target.xy, room, bounds)
        if p:
            cv2.circle(out, p, 13, CYAN, 1, cv2.LINE_AA)
            cv2.circle(out, p, 6, CYAN, -1, cv2.LINE_AA)
    for xy in radar_points:
        p = plot_point(xy, room, bounds)
        if p:
            cv2.drawMarker(out, p, AMBER, cv2.MARKER_DIAMOND, 15, 2)

    label(out, "TARGET", 28, 601, 0.46, MUTED)
    status = f"PERSON {target.track_id}" if live else "NO FRESH CAMERA TARGET"
    label(out, status, 28, 635, 0.65, CYAN if live else MUTED, 2)
    label(out, "POSITION", 366, 601, 0.46, MUTED)
    pos = f"x {target.xy[0]:.2f} / y {target.xy[1]:.2f} m" if live else "--"
    label(out, pos, 366, 635, 0.65, INK, 2)
    label(out, "CAMERA MODEL", 830, 601, 0.46, MUTED)
    label(out, "CALIBRATED FLOOR" if calibrated else "APPROXIMATE DISTANCE",
          830, 634, 0.53, GREEN if calibrated else AMBER, 1)
    label(out, f"{fps:.1f} FPS   |   CAMERA: cyan   RADAR: amber", 28, 684, 0.47, MUTED)
    label(out, f"RADAR: {radar_status}"[:51], 700, 684, 0.45, AMBER)
    if live and plot_point(target.xy, room, bounds) is None:
        label(out, "TARGET OUTSIDE REFERENCE AREA", 844, 551, 0.42, AMBER)
    return out


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--camera2", type=int, help="second webcam index; enables two-camera view")
    p.add_argument("--camera-test", action="store_true", help="live camera identification without detection")
    p.add_argument("--position-source", choices=["stereo", "radar"], default="stereo",
                   help="radar uses LD2450 position plus independent, uncropped camera coverage")
    p.add_argument("--map-objects", action="store_true", help="radar mode: detect floor-standing furniture and map approximate floor anchors")
    p.add_argument("--object-floor", type=Path, help="left camera floor calibration for objects")
    p.add_argument("--object-floor2", type=Path, help="right camera floor calibration for objects")
    p.add_argument("--baseline", type=float, default=0.40,
                   help="left-to-right lens spacing in metres (two-camera mode)")
    p.add_argument("--camera2-x", type=float)
    p.add_argument("--camera2-y", type=float, default=0.0)
    p.add_argument("--camera2-yaw", type=float, default=0.0)
    p.add_argument("--homography2", type=Path, help="separate floor calibration for camera 2")
    p.add_argument("--hfov2", type=float, default=70)
    p.add_argument("--capture-width", type=int, default=640)
    p.add_argument("--capture-height", type=int, default=480)
    p.add_argument("--capture-fps", type=float, default=15)
    p.add_argument("--camera-api", choices=["auto", "dshow", "msmf"], default="auto")
    p.add_argument("--dashboard-width", type=int, default=0,
                   help="0 renders at the window's pixel size; override with 1920, 2560 or 3840")
    p.add_argument("--record-width", type=int, default=1280,
                   help="fixed 16:9 recording width; use 1920 for Full HD (default 1280)")
    p.add_argument("--independent-cameras", action="store_true", help="legacy diagnostic with separate camera tracks")
    p.add_argument("--stereo-calibration", type=Path, default=BASE / "calib" / "stereo.json")
    p.add_argument("--stereo-floor", type=Path, help="left-camera measured floor points for 3D-to-room alignment")
    p.add_argument("--max-pair-skew-ms", type=float, default=40,
                   help="maximum host receipt-time difference for stereo pairs (webcams are not hardware synchronized)")
    p.add_argument("--stereo-num-disparities", type=int, default=0, help="0 chooses range from calibrated focal length/baseline")
    p.add_argument("--stereo-min-depth", type=float, default=0.7)
    p.add_argument("--stereo-max-depth", type=float, default=6.0)
    p.add_argument("--video", type=Path, help="use a recorded input; displayed as replay")
    p.add_argument("--model", type=Path, default=BASE / "yolov8n.pt")
    p.add_argument("--room-width", type=float, default=5.0, help="camera-wall length in metres")
    p.add_argument("--room-depth", type=float, default=4.0, help="distance into room in metres")
    p.add_argument("--camera-x", type=float)
    p.add_argument("--camera-y", type=float, default=0.0)
    p.add_argument("--camera-yaw", type=float, default=0.0)
    p.add_argument("--person-height", type=float, default=1.7)
    p.add_argument("--hfov", type=float, default=70)
    p.add_argument("--homography", type=Path)
    p.add_argument("--radar-port", help="optional real LD2450 COM port (256000 baud)")
    p.add_argument("--radar-x", type=float)
    p.add_argument("--radar-y", type=float, default=0.0)
    p.add_argument("--radar-yaw", type=float, default=0.0)
    p.add_argument("--record", type=Path, help="save overlay MP4 plus measurements CSV")
    p.add_argument("--seconds", type=float, default=0, help="stop after N seconds; 0 means until Q")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--preview", type=Path, help="save labelled layout preview, without opening sensors")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.headless and not args.preview:
        from .dashboard_display import enable_dpi_awareness
        enable_dpi_awareness()
    import cv2
    if not all(math.isfinite(v) and v > 0 for v in (args.room_width, args.room_depth)):
        raise SystemExit("Room dimensions must be positive, finite metres.")
    if (args.map_objects or args.object_floor or args.object_floor2) and args.position_source != "radar":
        raise SystemExit("Object mapping uses --position-source radar.")
    if args.position_source == "radar" and not args.camera_test:
        from .mapping_radar import run
        return run(args)
    if args.camera2 is not None and not args.camera_test and not args.independent_cameras:
        from .mapping_stereo import run
        return run(args)
    if args.camera2 is not None or args.camera_test:
        from .mapping_multi import run
        return run(args)
    if args.homography2:
        raise SystemExit("--homography2 requires --camera2.")
    room = (args.room_width, args.room_depth)
    cx = args.room_width / 2 if args.camera_x is None else args.camera_x
    pose = (cx, args.camera_y, args.camera_yaw)
    target = TargetState()
    if args.preview:
        from ..vision.detector import Track
        img = np.full((480, 640, 3), (57, 53, 47), np.uint8)
        label(img, "LAYOUT PREVIEW", 120, 180, 1.0, MUTED, 2)
        tracks = [Track(1, 235, 140, 370, 440, 0.94)]
        target.observe(2.2, 2.4, 1, 1.0)
        overlay = render_overlay(img, tracks, target, now=1.0, room=room,
                                 camera_pose=pose, radar_points=[(2.4, 2.5)],
                                 radar_status="PREVIEW ONLY", preview=True)
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.preview), overlay):
            raise SystemExit("Could not save preview.")
        print(args.preview.resolve())
        return 0

    from ..vision.sources import make_source
    from ..vision.detector import PersonDetector, select_primary
    from ..vision.geometry import FloorHomography, MonocularEstimator, RoomProjector
    source = make_source("video" if args.video else "webcam",
                         str(args.video) if args.video else str(args.camera))
    radar, writer, csv_file = None, None, None
    count = 0
    start = time.monotonic()
    locked_id = None
    last, fps = start, 0.0
    last_radar_frame = 0
    try:
        detector = PersonDetector(str(args.model))
        projector = None
        if args.homography:
            projector = RoomProjector.from_homography(FloorHomography.load(args.homography))
        if args.radar_port:
            rx = cx if args.radar_x is None else args.radar_x
            radar = RadarFeed(args.radar_port, (rx, args.radar_y, args.radar_yaw))
            radar.start()
        rows = None
        if args.record:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(args.record), cv2.VideoWriter_fourcc(*"mp4v"),
                                     15.0, (1280, 720))
            if not writer.isOpened():
                raise RuntimeError(f"Could not create {args.record}")
            csv_file = args.record.with_suffix(".csv").open("w", newline="", encoding="utf-8")
            rows = csv.writer(csv_file)
            rows.writerow(["elapsed_s", "source", "track_id", "x_m", "y_m", "calibration"])
        start = last = next_record = time.monotonic()
        print("Mapping observer started. Q quit | L lock/unlock current person | C clear trail", flush=True)
        print("Camera cyan; radar amber. No flight commands. No simulated targets.", flush=True)
        for frame in source:
            if projector is None:
                hh, ww = frame.image.shape[:2]
                projector = RoomProjector.from_monocular(
                    MonocularEstimator(ww, hh, args.hfov, args.person_height), pose)
            tracks = detector.track(frame.image)
            primary = (next((t for t in tracks if t.track_id == locked_id), None)
                       if locked_id is not None else select_primary(tracks))
            now = time.monotonic()
            dt = max(0.001, now - last)
            fps = 1 / dt if not fps else 0.85 * fps + 0.15 / dt
            last = now
            if primary is not None:
                fix = projector.locate(primary)
                # A slow inference result is not presented as a fresh measurement.
                if now - frame.t_mono <= target.stale_s:
                    target.observe(fix.x_m, fix.y_m, primary.track_id, frame.t_mono)
                    if rows:
                        rows.writerow([f"{now-start:.3f}", "camera", primary.track_id,
                                       f"{fix.x_m:.3f}", f"{fix.y_m:.3f}", fix.method])
            radar_points, radar_status = [], "NOT CONNECTED"
            if radar:
                radar_points, rn, error, age = radar.snapshot(now)
                radar_status = ("WAITING FOR REPORTS" if rn == 0 and error in ("opening", "waiting for reports") else
                                "ERROR / CHECK PORT" if error and rn == 0 else
                                "STALE" if age > 0.8 else f"LIVE / {len(radar_points)} TARGETS")
                if rows and rn != last_radar_frame and age <= 0.8:
                    for i, (x, y) in enumerate(radar_points):
                        rows.writerow([f"{now-start:.3f}", "radar", i,
                                       f"{x:.3f}", f"{y:.3f}", "sensor frame + configured pose"])
                last_radar_frame = rn
            overlay = render_overlay(frame.image, tracks, target, now=now, room=room,
                                     camera_pose=pose, fps=fps, calibrated=bool(args.homography),
                                     radar_points=radar_points, radar_status=radar_status,
                                     recording=writer is not None)
            if args.video:
                cv2.rectangle(overlay, (860, 15), (1220, 62), BG, -1)
                label(overlay, "RECORDED INPUT / REPLAY", 870, 43, 0.54, AMBER)
            if writer:
                while next_record <= now:
                    writer.write(overlay)
                    next_record += 1 / 15
                if count % 30 == 0:
                    csv_file.flush()
            count += 1
            if not args.headless:
                cv2.imshow("Kogane room map - Q quit, L lock, C clear", overlay)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("l"):
                    locked_id = None if locked_id is not None else (
                        primary.track_id if primary else None)
                    target.clear()
                if key == ord("c"):
                    target.trail.clear()
            if args.seconds and now - start >= args.seconds:
                break
        if not count:
            raise RuntimeError("Camera opened but no frames arrived. Check camera/privacy settings.")
        print(f"Observed {count} real camera frames.")
        if args.record:
            print(f"Recording: {args.record.resolve()}\nMeasurements: {args.record.with_suffix('.csv').resolve()}")
        return 0
    finally:
        source.release()
        if radar:
            radar.close()
        if writer:
            writer.release()
        if csv_file:
            csv_file.close()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Mapping stopped: {exc}\nCheck the webcam connection/index and close other camera apps.")
        raise SystemExit(1)
