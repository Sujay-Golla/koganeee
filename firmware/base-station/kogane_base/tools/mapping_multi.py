"""Two independent webcams in one room map. No stereo or cross-camera identity claim.

Capture threads keep the latest frame so a slow/failed camera cannot stall the other.
Each camera owns its detector/tracker and room projector. No flight/network output.
"""
from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass, field
import math
import os
import threading
import time

import numpy as np

from .mapping_demo import (AMBER, BG, CARD, CYAN, GREEN, INK, MUTED, PURPLE,
                           RadarFeed, TargetState, label, plot_point)


def camera_poses(args):
    """Default optical centres straddle the wall midpoint by the measured baseline."""
    if args.camera2 == args.camera:
        raise ValueError("Choose different camera indices for --camera and --camera2.")
    if not math.isfinite(args.baseline) or args.baseline <= 0:
        raise ValueError("--baseline must be a positive distance in metres.")
    middle = args.room_width / 2
    left_x = args.camera_x if args.camera_x is not None else (
        middle - args.baseline / 2 if args.camera2 is not None else middle)
    right_x = args.camera2_x if args.camera2_x is not None else left_x + args.baseline
    poses = [(left_x, args.camera_y, args.camera_yaw)]
    if args.camera2 is not None:
        poses.append((right_x, args.camera2_y, args.camera2_yaw))
    if not all(math.isfinite(v) for pose in poses for v in pose):
        raise ValueError("Camera positions and angles must be finite numbers.")
    return poses


class LatestCamera:
    """Own VideoCapture on its reader thread; publish only its latest complete image."""

    def __init__(self, index, *, width=640, height=480, fps=15, api="auto"):
        self.index = index
        self.width, self.height, self.fps, self.api = width, height, fps, api
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.frame = None
        self.frames = deque(maxlen=20)
        self.sequence = 0
        self.status = "OPENING"
        self.thread = threading.Thread(target=self._read, daemon=True)

    def start(self):
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return self.frame, self.sequence, self.status

    def history(self):
        with self.lock:
            return list(self.frames), self.status

    def _read(self):
        import cv2
        from ..vision.sources import Frame
        cap = None
        try:
            # DirectShow often handles two independent USB webcams better on Windows.
            api = self.api
            if api == "auto":
                api = "dshow" if os.name == "nt" else "auto"
            backend = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW,
                       "msmf": cv2.CAP_MSMF}[api]
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                raise RuntimeError("could not open; check index / camera in use")
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while not self.stop.is_set():
                ok, image = cap.read()
                timestamp = time.monotonic()
                if not ok or image is None:
                    raise RuntimeError("capture stopped / camera disconnected")
                with self.lock:
                    self.sequence += 1
                    self.frame = Frame(image, self.sequence, timestamp)
                    self.frames.append(self.frame)
                    self.status = "LIVE"
        except Exception as exc:
            with self.lock:
                self.frame = None
                self.frames.clear()
                self.status = str(exc)
        finally:
            if cap is not None:
                cap.release()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1.5)


@dataclass
class CameraView:
    index: int
    pose: tuple
    color: tuple = CYAN
    target: TargetState = field(default_factory=TargetState)
    frame: object = None
    tracks: list = field(default_factory=list)
    objects: list = field(default_factory=list)
    object_status: str = ""
    status: str = "OPENING"
    processed: int = 0
    locked_id: int | None = None
    projector: object = None
    detector: object = None
    calibrated: bool = False
    fps: float = 0.0
    last_processed: float = 0.0

    def frame_live(self, now):
        return self.status == "LIVE" and self.frame is not None and 0 <= now - self.frame.t_mono <= 0.8


def consume(view, frame, sequence, status, *, now, testing, hfov, height):
    """Consume each image once. Never reuse a detection on a later camera frame."""
    view.status = status
    if status != "LIVE" or frame is None:
        view.frame = None
        view.tracks = []
        view.target.clear()
        return None
    if sequence == view.processed:
        return None
    view.frame, view.processed = frame, sequence
    if now - frame.t_mono > 0.8:
        view.tracks = []
        return None
    if view.last_processed:
        rate = 1 / max(0.001, now - view.last_processed)
        view.fps = rate if not view.fps else 0.8 * view.fps + 0.2 * rate
    view.last_processed = now
    if testing:
        return None
    from ..vision.detector import select_primary
    from ..vision.geometry import MonocularEstimator, RoomProjector
    if view.projector is None:
        hh, ww = frame.image.shape[:2]
        view.projector = RoomProjector.from_monocular(
            MonocularEstimator(ww, hh, hfov, height), view.pose)
    elif view.calibrated:
        hom = view.projector.homography
        size = (frame.image.shape[1], frame.image.shape[0])
        if hom.img_size is not None and hom.img_size != size:
            raise ValueError(f"Camera {view.index}: calibration size {hom.img_size} differs from {size}; recalibrate at the capture resolution.")
    view.tracks = view.detector.track(frame.image)
    primary = (next((t for t in view.tracks if t.track_id == view.locked_id), None)
               if view.locked_id is not None else select_primary(view.tracks))
    if primary is None or time.monotonic() - frame.t_mono > view.target.stale_s:
        return None
    fix = view.projector.locate(primary)
    if view.target.observe(fix.x_m, fix.y_m, primary.track_id, frame.t_mono):
        return primary.track_id, fix
    return None


def render(views, *, now, room, radar_points=(), radar_status="NOT CONNECTED",
           testing=False, recording=False, preview=False, stereo=None):
    import cv2
    out = np.full((720, 1280, 3), BG, np.uint8)
    label(out, "KOGANE", 28, 46, 1.05, INK, 2)
    label(out, "CAMERA CONNECTION TEST" if testing else "STEREO PERSON TRACKING" if stereo else "TWO-CAMERA ROOM TRACKING", 220, 44, 0.6, CYAN)
    limited = stereo and stereo.get("calibration_warning", False)
    label(out, "LAYOUT PREVIEW / NOT LIVE" if preview else "LIMITED CALIBRATION / CHECK RANGE" if limited else "LIVE SENSOR VIEW", 900, 43, 0.41 if limited else 0.49,
          AMBER if preview or limited else GREEN)
    if recording:
        cv2.circle(out, (1243, 38), 6, (65, 65, 245), -1)

    for i, view in enumerate(views):
        row = 77 + i * 282
        live = view.frame_live(now)
        state = "LIVE" if live else ("STALE / NO CURRENT FRAME" if view.status == "LIVE" else view.status)
        label(out, f"CAMERA {i+1} / DEVICE {view.index}", 28, row + 10, 0.53, view.color, 1)
        label(out, state[:62], 300, row + 10, 0.40, GREEN if live else AMBER)
        x, y, w, h = 28, row + 24, 760, 225
        cv2.rectangle(out, (x, y), (x+w, y+h), CARD, -1)
        if live:
            img = view.frame.image.copy()
            for track in view.tracks:
                color = view.color if track.track_id == view.target.track_id else MUTED
                p1, p2 = (int(track.x1), int(track.y1)), (int(track.x2), int(track.y2))
                cv2.rectangle(img, p1, p2, color, 2)
                caption = f"PERSON {track.track_id}" if stereo else f"C{i+1} ID {track.track_id}"
                label(img, caption, p1[0], max(20, p1[1]-6), 0.5, color)
            ih, iw = img.shape[:2]
            scale = min(w / iw, h / ih)
            rw, rh = max(1, round(iw*scale)), max(1, round(ih*scale))
            px, py = x+(w-rw)//2, y+(h-rh)//2
            out[py:py+rh, px:px+rw] = cv2.resize(img, (rw, rh))
        else:
            label(out, "CHECK CAMERA / USB / PRIVACY SETTINGS", x+40, y+110, 0.57, AMBER)
        model = ("RECTIFIED LEFT / PERSON DETECTION" if i == 0 else "RECTIFIED RIGHT / STEREO MATCH") if stereo else "CAMERA TEST / DETECTION OFF" if testing else (
            "CALIBRATED FLOOR" if view.calibrated else "APPROXIMATE DISTANCE")
        label(out, f"{model} | {view.fps:.1f} updates/s", 28, row+269, 0.43, MUTED)

    cv2.rectangle(out, (816, 76), (1253, 633), CARD, -1)
    label(out, "SHARED POSITION MAP", 842, 108, 0.61, INK)
    w, h = room
    label(out, f"{w:g} x {h:g} m reference area", 842, 137, 0.47, MUTED)
    scale = min(330/w, 350/h)
    pw, ph = round(w*scale), round(h*scale)
    left, top = 1035-pw//2, 171
    bounds = (left, top, left+pw, top+ph)
    for gx in np.arange(0, w+.001, 1):
        p = plot_point((float(gx), 0), room, bounds)
        if p:
            cv2.line(out, (p[0], top), (p[0], top+ph), (65, 58, 47), 1)
    for gy in np.arange(0, h+.001, 1):
        p = plot_point((0, float(gy)), room, bounds)
        if p:
            cv2.line(out, (left, p[1]), (left+pw, p[1]), (65, 58, 47), 1)
    cv2.rectangle(out, (left, top), (left+pw, top+ph), MUTED, 1)
    for i, view in enumerate(views):
        cam = plot_point(view.pose[:2], room, bounds)
        if cam:
            cv2.drawMarker(out, cam, view.color, cv2.MARKER_TRIANGLE_UP, 12, 2)
            angle = math.radians(view.pose[2])
            tip = plot_point((view.pose[0]-0.3*math.sin(angle), view.pose[1]+0.3*math.cos(angle)), room, bounds)
            if tip:
                cv2.line(out, cam, tip, view.color, 2)
        if stereo:
            continue
        for a, b in zip(view.target.trail, list(view.target.trail)[1:]):
            pa, pb = plot_point(a, room, bounds), plot_point(b, room, bounds)
            if pa and pb:
                cv2.line(out, pa, pb, tuple(int(c*.6) for c in view.color), 2, cv2.LINE_AA)
        fresh = view.frame_live(now) and view.target.fresh(now)
        if fresh:
            point = plot_point(view.target.xy, room, bounds)
            if point:
                cv2.circle(out, point, 8, view.color, 2)
                label(out, f"C{i+1}", point[0]+10, point[1]-8, 0.4, view.color)
        position = (f"{view.target.xy[0]:.2f}, {view.target.xy[1]:.2f} m" if fresh else "NO FRESH TARGET")
        label(out, f"C{i+1}: {position}", 842, 555+i*26, 0.47, view.color)
        if fresh and plot_point(view.target.xy, room, bounds) is None:
            label(out, f"C{i+1} OUTSIDE AREA", 842, 158, 0.4, AMBER)
    if stereo:
        target = stereo["target"]
        fresh = stereo["valid"] and target.fresh(now)
        for a, b in zip(target.trail, list(target.trail)[1:]):
            pa, pb = plot_point(a, room, bounds), plot_point(b, room, bounds)
            if pa and pb:
                cv2.line(out, pa, pb, (105, 135, 70), 2, cv2.LINE_AA)
        if fresh:
            point = plot_point(target.xy, room, bounds)
            if point:
                cv2.circle(out, point, 12, GREEN, 2)
                cv2.circle(out, point, 5, GREEN, -1)
                label(out, f"PERSON {target.track_id}", point[0]+12, point[1]-9, .4, GREEN)
            else:
                label(out, "TARGET OUTSIDE ROOM AREA", 842, 159, .4, AMBER)
        position = f"x {target.xy[0]:.2f} / y {target.xy[1]:.2f} m" if fresh else "NO VALID STEREO POSITION"
        label(out, position, 842, 555, .48, GREEN if fresh else AMBER)
        label(out, stereo["detail"][:51] if fresh else stereo["status"][:51], 842, 581, .4, INK)
        label(out, stereo["alignment"], 842, 609, .4, MUTED)
    for xy in radar_points:
        point = plot_point(xy, room, bounds)
        if point:
            cv2.drawMarker(out, point, AMBER, cv2.MARKER_DIAMOND, 16, 2)
    label(out, "ONE STEREO PERSON green | RADAR amber" if stereo else "CAM 1 cyan | CAM 2 purple | RADAR amber", 28, 669, 0.48, MUTED)
    label(out, "Q quit | L lock person | C clear trail" if stereo else "Q quit | 1/2 lock camera target | C clear trails", 28, 698, 0.46, MUTED)
    label(out, f"RADAR: {radar_status}"[:48], 816, 667, 0.43, AMBER)
    label(out, stereo["status"][:53] if stereo else "INDEPENDENT TRACKS / PER-CAMERA IDS", 816, 697, 0.40, MUTED)
    return out


def run(args):
    import cv2
    if args.video:
        raise ValueError("Two-camera/test mode uses live webcams; omit --video.")
    if args.homography2 and args.camera2 is None:
        raise ValueError("--homography2 requires --camera2.")
    if not (args.capture_width > 0 and args.capture_height > 0 and
            math.isfinite(args.capture_fps) and args.capture_fps > 0):
        raise ValueError("Capture width, height and FPS must be positive.")
    if not all(math.isfinite(v) and 0 < v < 180 for v in (args.hfov, args.hfov2)):
        raise ValueError("Camera horizontal fields of view must be between 0 and 180 degrees.")
    if not math.isfinite(args.person_height) or args.person_height <= 0:
        raise ValueError("Assumed person height must be positive metres.")
    poses = camera_poses(args)
    indices = [args.camera] + ([args.camera2] if args.camera2 is not None else [])
    views = [CameraView(idx, pose, color) for idx, pose, color in zip(indices, poses, (CYAN, PURPLE))]
    room = (args.room_width, args.room_depth)
    if args.preview:
        from ..vision.sources import Frame
        from ..vision.detector import Track
        for i, view in enumerate(views):
            img = np.full((480, 640, 3), (57, 53, 47), np.uint8)
            label(img, "LAYOUT PREVIEW", 120, 220, 0.8, MUTED)
            view.frame, view.status = Frame(img, 1, 1), "LIVE"
            view.tracks = [Track(1, 220, 70, 370, 450, .9)]
            view.target.observe(2+i*.15, 2.5, 1, 1)
        overlay = render(views, now=1, room=room, radar_points=[(2.1, 2.6)],
                         radar_status="PREVIEW ONLY", testing=args.camera_test, preview=True)
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.preview), overlay):
            raise RuntimeError("Could not save preview.")
        print(args.preview.resolve())
        return 0

    readers, radar, writer, csv_file = [], None, None, None
    counts = [0] * len(views)
    radar_frames = 0
    try:
        # Separate model instances are intentional: persistent tracker IDs belong to one camera.
        if not args.camera_test:
            from ..vision.detector import PersonDetector
            from ..vision.geometry import FloorHomography, RoomProjector
            print("Loading and warming up each camera's person tracker...", flush=True)
            for view, path in zip(views, (args.homography, args.homography2)):
                view.detector = PersonDetector(str(args.model))
                view.detector.track(np.zeros((args.capture_height, args.capture_width, 3), np.uint8))
                if path:
                    view.projector = RoomProjector.from_homography(FloorHomography.load(path))
                    view.calibrated = True
        for idx in indices:
            reader = LatestCamera(idx, width=args.capture_width, height=args.capture_height,
                                  fps=args.capture_fps, api=args.camera_api)
            readers.append(reader)
            reader.start()
        if args.radar_port:
            x = args.room_width/2 if args.radar_x is None else args.radar_x
            radar = RadarFeed(args.radar_port, (x, args.radar_y, args.radar_yaw))
            radar.start()
        rows = None
        if args.record:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(args.record), cv2.VideoWriter_fourcc(*"mp4v"), 15, (1280, 720))
            if not writer.isOpened():
                raise RuntimeError(f"Could not create {args.record}")
            csv_file = args.record.with_suffix(".csv").open("w", newline="", encoding="utf-8")
            rows = csv.writer(csv_file)
            rows.writerow(["elapsed_s", "source", "device", "track_id", "x_m", "y_m", "calibration"])
        start = next_record = time.monotonic()
        last_flush = start
        print(f"Webcam indices {indices}; capture {args.capture_width}x{args.capture_height} at requested {args.capture_fps:g} FPS.", flush=True)
        print("Q quit | 1/2 lock each camera target | C clear trails. Cameras have independent IDs; no flight commands.", flush=True)
        while True:
            for i, (view, reader) in enumerate(zip(views, readers)):
                frame, sequence, status = reader.snapshot()
                previous = view.processed
                result = consume(view, frame, sequence, status, now=time.monotonic(), testing=args.camera_test,
                                 hfov=(args.hfov, args.hfov2)[i], height=args.person_height)
                if view.processed != previous:
                    counts[i] += 1
                if rows and result:
                    track_id, fix = result
                    rows.writerow([f"{time.monotonic()-start:.3f}", f"camera{i+1}", view.index,
                                   track_id, f"{fix.x_m:.3f}", f"{fix.y_m:.3f}", fix.method])
            now = time.monotonic()
            points, radar_status = [], "NOT CONNECTED"
            if radar:
                points, rn, error, age = radar.snapshot(now)
                radar_status = ("ERROR / CHECK PORT" if error not in ("", "opening", "waiting for reports") else
                                "WAITING FOR REPORTS" if rn == 0 else "STALE" if age > .8 else f"LIVE / {len(points)} TARGETS")
                if rows and rn != radar_frames and age <= .8:
                    for i, (x, y) in enumerate(points):
                        rows.writerow([f"{now-start:.3f}", "radar", args.radar_port, i,
                                       f"{x:.3f}", f"{y:.3f}", "sensor frame + configured pose"])
                radar_frames = rn
            overlay = render(views, now=now, room=room, radar_points=points, radar_status=radar_status,
                             testing=args.camera_test, recording=writer is not None)
            if writer:
                while next_record <= now:
                    writer.write(overlay)
                    next_record += 1/15
                if now-last_flush > 1:
                    csv_file.flush()
                    last_flush = now
            if not args.headless:
                cv2.imshow("Kogane two-camera map - Q quit", overlay)
                key = cv2.waitKey(10) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("c"):
                    for view in views:
                        view.target.trail.clear()
                if key in (ord("1"), ord("2")):
                    i = key-ord("1")
                    if i < len(views):
                        from ..vision.detector import select_primary
                        view = views[i]
                        primary = select_primary(view.tracks)
                        view.locked_id = None if view.locked_id is not None else (primary.track_id if primary else None)
                        view.target.clear()
            else:
                time.sleep(.01)
            if args.seconds and now-start >= args.seconds:
                break
            if not any(counts) and now-start > 15:
                raise RuntimeError("No camera frames after 15 seconds. Check indices, camera permissions, USB ports or --camera-api msmf.")
        print(f"Real frames processed per camera: {dict(zip(indices, counts))}")
        if args.record:
            print(f"Saved {args.record.resolve()} and {args.record.with_suffix('.csv').resolve()}")
        if not all(counts):
            print("At least one requested camera produced no frames; inspect its status in the overlay.")
            return 2
        return 0
    finally:
        for reader in readers:
            reader.close()
        if radar:
            radar.close()
        if writer:
            writer.release()
        if csv_file:
            csv_file.close()
        if not args.headless:
            cv2.destroyAllWindows()
