"""LD2450 position with two independent, unrectified camera views for coverage."""
from __future__ import annotations

import csv
import math
import time

import numpy as np

from .mapping_demo import RadarFeed, TargetState
from .mapping_multi import CameraView, LatestCamera, camera_poses
from .mapping_ui import render
from .dashboard_display import enable_dpi_awareness, render_size, recording_frame, size_from_width
from ..vision.sources import Frame


class SingleRadarTrack:
    """Single-person demo: never pick an arbitrary target from multiple reports."""

    def __init__(self, pose):
        self.pose = pose
        self.target = TargetState()
        self.frames = 0
        self.distance_m = None
        self.valid = False
        self.status = "WAITING FOR RADAR"
        self.last_raw = None
        self.last_time = None
        self.identity = 1

    def update(self, points, frames, error, age, now):
        self.valid = False
        self.distance_m = None
        if error not in ("", "opening", "waiting for reports"):
            self.status = "RADAR ERROR"
            return False
        if not frames:
            self.status = "WAITING FOR RADAR"
            return False
        if not math.isfinite(age) or not 0 <= age <= self.target.stale_s:
            self.status = "RADAR PAUSED"
            return False
        if not points:
            self.frames = frames
            self.status = "NO RADAR TARGET"
            return False
        if len(points) != 1:
            self.frames = frames
            self.status = "MULTIPLE RADAR TARGETS"
            return False
        xy = points[0]
        if not all(math.isfinite(v) for v in xy):
            self.status = "INVALID RADAR POSITION"
            return False
        is_new = frames != self.frames
        if is_new:
            timestamp = now-age
            if self.last_raw is not None and self.last_time is not None:
                dt = timestamp-self.last_time
                jump = math.dist(xy, self.last_raw)
                if dt > self.target.stale_s or jump > .5+3*max(0, dt):
                    self.identity += 1
                    self.target.clear()
            self.frames = frames
            if not self.target.observe(*xy, self.identity, timestamp):
                self.status = "INVALID RADAR POSITION"
                return False
            self.last_raw, self.last_time = xy, timestamp
        self.valid = self.target.fresh(now)
        self.status = "RADAR POSITION VALID" if self.valid else "RADAR PAUSED"
        if self.valid:
            self.distance_m = math.dist(self.target.xy, self.pose[:2])
        return is_new and self.valid


def consume_camera(view, frame, sequence, status, now):
    """Boxes are local to this view; camera visibility never changes radar position."""
    view.status = status
    if frame is None or status != "LIVE":
        view.frame, view.tracks, view.objects = None, [], []
        return False
    if sequence == view.processed:
        return False
    view.processed, view.frame, view.tracks, view.objects = sequence, frame, [], []
    if not 0 <= now-frame.t_mono <= .8:
        return False
    if view.last_processed:
        view.fps = 1/max(.001, now-view.last_processed)
    view.last_processed = now
    # Full original frame: no stereo remapping, cropping, or image pairing.
    view.tracks = view.detector.track(frame.image)
    view.objects = list(getattr(view.detector, "objects", []))
    return True


def run(args):
    import cv2
    from ..vision.detector import PersonDetector, Track
    record_size = size_from_width(args.record_width)
    if args.dashboard_width:
        size_from_width(args.dashboard_width)
    if args.camera2 is None or args.camera2 == args.camera:
        raise ValueError("Radar coverage mode needs two different camera indices; a missing camera can remain disconnected.")
    if not args.radar_port and not args.preview:
        raise ValueError("Radar position needs --radar-port, for example --radar-port COM6.")
    if args.video or args.homography or args.homography2 or args.stereo_floor or args.independent_cameras:
        raise ValueError("Radar coverage mode uses raw live cameras and radar placement; omit video, floor-calibration and independent-camera options.")
    if not (args.capture_width > 0 and args.capture_height > 0 and math.isfinite(args.capture_fps) and args.capture_fps > 0):
        raise ValueError("Capture dimensions and FPS must be positive.")
    if (args.object_floor or args.object_floor2) and not args.map_objects:
        raise ValueError("Add --map-objects to use object floor calibration files.")
    poses = camera_poses(args)
    views = [CameraView(idx, pose) for idx, pose in zip((args.camera, args.camera2), poses)]
    radar_x = (poses[0][0]+poses[1][0])/2 if args.radar_x is None else args.radar_x
    pose = (radar_x, args.radar_y, args.radar_yaw)
    if not all(math.isfinite(v) for v in pose):
        raise ValueError("Radar placement must use finite metres/degrees.")
    tracker = SingleRadarTrack(pose)
    room = (args.room_width, args.room_depth)
    object_mapper = None
    if args.map_objects:
        from ..vision.objects import ObjectMapper, SceneDetector, load_floor
        floors = {view.index: load_floor(path) for view, path in
                  zip(views, (args.object_floor, args.object_floor2)) if path}
        object_mapper = ObjectMapper(room, floors)
    state = dict(target=tracker.target, valid=False, depth_m=None, position_source="radar",
                 status="WAITING FOR RADAR", room_aligned=False, calibration_warning=False,
                 radar_pose=pose, show_details=False, show_cameras=False, elapsed_s=0)
    state.update(map_objects=args.map_objects, objects=[])
    if args.preview:
        for i, view in enumerate(views):
            image = np.full((480, 640, 3), 45+i*10, np.uint8)
            view.frame, view.status = Frame(image, 1, 1), "LIVE"
            view.tracks = [Track(i+1, 170+i*140, 60, 320+i*140, 450, .9)]
        for i in range(24):
            tracker.update([(1.6+i*.04, 1.3+i*.04)], i+1, "", 0, i/23)
        state.update(valid=True, depth_m=tracker.distance_m, status=tracker.status)
        if args.map_objects:
            # Explicit example anchors, never introduced in a live run.
            state["objects"] = [dict(identity=1, label="Chair", xy=(1.3, 2.7), age_s=0,
                                     visible=True, cameras=[args.camera]),
                                dict(identity=2, label="Plant", xy=(3.8, 3.2), age_s=4,
                                     visible=False, cameras=[])]
            for view in views:
                view.object_status = "Example floor anchors"
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.preview), render(views, now=1, room=room, stereo=state,
                                             radar_points=[tracker.target.xy], radar_status="PREVIEW ONLY", preview=True,
                                             size=render_size(forced_width=args.dashboard_width)))
        print(args.preview.resolve())
        return 0

    readers, radar, writer, csv_file, objects_file = [], None, None, None, None
    camera_counts, fixes = [0, 0], 0
    try:
        print("Loading camera detectors. Person position comes only from radar; optional furniture anchors come from floor calibration.", flush=True)
        for view in views:
            view.detector = SceneDetector(str(args.model)) if args.map_objects else PersonDetector(str(args.model))
            view.detector.track(np.zeros((args.capture_height, args.capture_width, 3), np.uint8))
        for view in views:
            reader = LatestCamera(view.index, width=args.capture_width, height=args.capture_height,
                                  fps=args.capture_fps, api=args.camera_api)
            readers.append(reader)
            reader.start()
        radar = RadarFeed(args.radar_port, pose)
        radar.start()
        rows = object_rows = None
        if args.record:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(args.record), cv2.VideoWriter_fourcc(*"mp4v"), 15, record_size)
            if not writer.isOpened():
                raise ValueError(f"Could not create {args.record}")
            csv_file = args.record.with_suffix(".csv").open("w", newline="", encoding="utf-8")
            rows = csv.writer(csv_file)
            rows.writerow(["elapsed_s", "source", "track_id", "x_m", "y_m", "distance_m", "placement"])
            if args.map_objects:
                objects_file = args.record.with_name(args.record.stem+"_objects.csv").open("w", newline="", encoding="utf-8")
                object_rows = csv.writer(objects_file)
                object_rows.writerow(["elapsed_s", "source", "camera", "object_id", "label", "x_m", "y_m", "confidence", "placement"])
        start = next_record = last_flush = time.monotonic()
        window, fullscreen = "Kogane | Radar + camera coverage", False
        if not args.headless:
            enable_dpi_awareness()
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 1280, 720)
        print(f"Radar {args.radar_port}: main position. Cameras {args.camera}/{args.camera2}: original full-frame views.", flush=True)
        print("Q save/close | V enlarge camera views | F fullscreen | D details | C clear path | O clear remembered objects", flush=True)
        while True:
            for i, (view, reader) in enumerate(zip(views, readers)):
                frame, sequence, status = reader.snapshot()
                if consume_camera(view, frame, sequence, status, time.monotonic()):
                    camera_counts[i] += 1
            now = time.monotonic()
            if object_mapper:
                observations = object_mapper.observe_views(views, now)
                state["objects"] = object_mapper.snapshot(now)
                for view in views:
                    view.object_status = object_mapper.status.get(view.index, "Floor calibration needed")
                if object_rows:
                    for observation in observations:
                        object_rows.writerow([f"{observation['timestamp']-start:.3f}", "camera_floor_anchor",
                                              observation["camera"], observation["identity"], observation["label"],
                                              f"{observation['xy'][0]:.3f}", f"{observation['xy'][1]:.3f}",
                                              f"{observation['confidence']:.3f}", "approximate box bottom / calibrated floor"])
            points, rn, error, age = radar.snapshot(now)
            is_new = tracker.update(points, rn, error, age, now)
            state.update(valid=tracker.valid, depth_m=tracker.distance_m, status=tracker.status,
                         elapsed_s=now-start)
            radar_status = ("ERROR / CHECK PORT" if error not in ("", "opening", "waiting for reports") else
                            "WAITING FOR REPORTS" if not rn else "STALE" if age > .8 else f"LIVE / {len(points)} TARGETS")
            if is_new:
                fixes += 1
                if rows:
                    rows.writerow([f"{now-start:.3f}", "radar", tracker.target.track_id,
                                   f"{tracker.target.xy[0]:.3f}", f"{tracker.target.xy[1]:.3f}",
                                   f"{tracker.distance_m:.3f}", "configured radar pose"])
            overlay = render(views, now=now, room=room, stereo=state, radar_points=points,
                             radar_status=radar_status, recording=writer is not None,
                             size=render_size(None if args.headless else window,
                                              forced_width=args.dashboard_width,
                                              record_size=record_size if writer else None))
            if writer:
                encoded = recording_frame(overlay, record_size)
                while next_record <= now:
                    writer.write(encoded)
                    next_record += 1/15
                if now-last_flush > 1:
                    csv_file.flush()
                    if objects_file:
                        objects_file.flush()
                    last_flush = now
            if not args.headless:
                cv2.imshow(window, overlay)
                key = cv2.waitKey(10) & 0xff
                if ord("A") <= key <= ord("Z"):
                    key += 32
                if key == ord("q"):
                    break
                if key == ord("c"):
                    tracker.target.trail.clear()
                if key == ord("o") and object_mapper:
                    object_mapper.clear()
                if key == ord("d"):
                    state["show_details"] = not state["show_details"]
                    state["show_cameras"] = False
                if key == ord("v"):
                    state["show_cameras"] = not state["show_cameras"]
                    state["show_details"] = False
                if key == ord("f"):
                    fullscreen = not fullscreen
                    cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
            else:
                time.sleep(.01)
            if args.seconds and now-start >= args.seconds:
                break
        print(f"Radar positions: {fixes}; camera frames: {camera_counts}")
        if args.record:
            print(f"Saved {args.record.resolve()} and CSV.")
        if not fixes:
            print("No usable single-target radar position received. Check COM port, wiring and sensor view.")
        return 0 if fixes else 2
    finally:
        for reader in readers:
            reader.close()
        if radar:
            radar.close()
        if writer:
            writer.release()
        if csv_file:
            csv_file.close()
        if objects_file:
            objects_file.close()
        if not args.headless:
            cv2.destroyAllWindows()
