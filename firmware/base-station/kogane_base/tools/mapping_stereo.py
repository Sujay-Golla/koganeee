"""One person track from rectified binocular correspondence, optional raw radar overlay."""
from __future__ import annotations

import csv
import math
import time

import numpy as np

from .mapping_demo import CYAN, PURPLE, RadarFeed, TargetState
from .mapping_multi import CameraView, LatestCamera, camera_poses
from .mapping_ui import render
from .dashboard_display import enable_dpi_awareness, render_size, recording_frame, size_from_width
from ..vision.sources import Frame
from ..vision.stereo import PairSelector, RoomAlignment, StereoCalibration, StereoDepth, StereoError


def rig_to_room(xyz, left_pose):
    """Explicit level-camera assumption until measured floor alignment is supplied."""
    x, _, z = xyz
    ox, oy, yaw = left_pose
    angle = math.radians(yaw)
    return np.array((ox+x*math.cos(angle)-z*math.sin(angle),
                     oy+x*math.sin(angle)+z*math.cos(angle), np.nan))


def run(args):
    import cv2
    from ..vision.detector import PersonDetector, Track, select_primary
    record_size = size_from_width(args.record_width)
    if args.dashboard_width:
        size_from_width(args.dashboard_width)
    if args.video or args.homography or args.homography2:
        raise StereoError("Stereo mode uses live webcams and --stereo-calibration; use --stereo-floor for measured room alignment. Separate camera homographies do not calibrate stereo.")
    if args.camera2 is None or args.camera == args.camera2:
        raise StereoError("Stereo requires two different physical cameras, in left/right order.")
    if not (args.capture_width > 0 and args.capture_height > 0 and math.isfinite(args.capture_fps) and args.capture_fps > 0):
        raise StereoError("Capture dimensions and FPS must be positive.")
    poses = camera_poses(args)
    views = [CameraView(idx, pose, color) for idx, pose, color in zip(
        (args.camera, args.camera2), poses, (CYAN, PURPLE))]
    target = TargetState()
    room = (args.room_width, args.room_depth)
    stereo = dict(target=target, valid=False, detail="", status="WAITING FOR CAMERA PAIR",
                  alignment="ROOM AXES ASSUMED / CALIBRATE FLOOR", room_aligned=False,
                  depth_m=None, support_fraction=None, skew_ms=None,
                  show_details=False, locked=False, elapsed_s=0)
    radar_x = (poses[0][0]+poses[1][0])/2 if args.radar_x is None else args.radar_x
    stereo["radar_pose"] = (radar_x, args.radar_y, args.radar_yaw)
    if args.preview:
        for view in views:
            view.frame = Frame(np.full((480, 640, 3), 50, np.uint8), 1, 1)
            view.status = "LIVE"
            view.tracks = [Track(1, 220, 70, 380, 450, .9)]
            view.target.track_id = 1
        for i in range(24):
            target.observe(1.7+.8*i/23, 1.3+1.1*i/23, 1, i/23)
        stereo.update(valid=True, detail="Depth 2.40 m / support 45%", status="PREVIEW ONLY",
                      depth_m=2.4, support_fraction=.45, skew_ms=12, calibration_warning=True)
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.preview), render(views, now=1, room=room, stereo=stereo,
                                                   radar_points=[(2.6, 2.3)], radar_status="PREVIEW ONLY", preview=True,
                                                   size=render_size(forced_width=args.dashboard_width))):
            raise StereoError("Could not save preview.")
        print(args.preview.resolve())
        return 0

    calibration = StereoCalibration.load(args.stereo_calibration)
    calibration.validate_capture((args.camera, args.camera2),
                                 (args.capture_width, args.capture_height), args.baseline)
    depth = StereoDepth(calibration, args.stereo_num_disparities,
                         args.stereo_min_depth, args.stereo_max_depth)
    stereo["calibration_warning"] = bool(calibration.quality_notes)
    for note in calibration.quality_notes:
        print(f"Calibration note: {note}", flush=True)
    print(f"Stereo search: {depth.num_disparities}px; nominal near limit {depth.nominal_near_m:.2f}m. Start the range check farther away.", flush=True)
    alignment = RoomAlignment.from_floor(args.stereo_floor, calibration) if args.stereo_floor else None
    if alignment:
        stereo["alignment"] = f"ROOM FLOOR ALIGNED / {alignment.error_px:.1f}px fit"
        stereo["room_aligned"] = True
    selector = PairSelector(args.max_pair_skew_ms/1000)
    print("Loading one person tracker for the stereo rig...", flush=True)
    detector = PersonDetector(str(args.model))
    detector.track(np.zeros((args.capture_height, args.capture_width, 3), np.uint8))
    readers, radar, writer, csv_file = [], None, None, None
    locked_id, primary = None, None
    counts, measurements = [0, 0], 0
    last_pair, radar_frames = None, 0
    try:
        for index in (args.camera, args.camera2):
            reader = LatestCamera(index, width=args.capture_width, height=args.capture_height,
                                  fps=args.capture_fps, api=args.camera_api)
            readers.append(reader)
            reader.start()
        if args.radar_port:
            radar = RadarFeed(args.radar_port, stereo["radar_pose"])
            radar.start()
        rows = None
        if args.record:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(args.record), cv2.VideoWriter_fourcc(*"mp4v"), 15, record_size)
            if not writer.isOpened():
                raise StereoError(f"Could not create {args.record}")
            csv_file = args.record.with_suffix(".csv").open("w", newline="", encoding="utf-8")
            rows = csv.writer(csv_file)
            rows.writerow(["elapsed_s", "source", "track_id", "x_m", "y_m", "height_m",
                           "depth_m", "host_skew_ms", "inlier_samples", "depth_spread_m", "room_alignment"])
        start = next_record = last_flush = time.monotonic()
        print(f"STEREO: left {args.camera}, right {args.camera2}; calibrated baseline {calibration.baseline_m:.3f}m.", flush=True)
        print("Q save/close | F fullscreen | D details | V camera views | L lock person | C clear path.", flush=True)
        print("Webcams lack hardware sync. Walk slowly; depth is withheld when receipt timing/correspondence fails.", flush=True)
        window = "Kogane | Room tracking"
        fullscreen = False
        if not args.headless:
            enable_dpi_awareness()
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 1280, 720)
        while True:
            now = time.monotonic()
            histories = [r.history() for r in readers]
            for view, (frames, status) in zip(views, histories):
                if status != "LIVE":
                    view.status, view.frame, view.tracks = status, None, []
                    stereo.update(valid=False, status=f"CAMERA {view.index}: {status}")
            pair = selector.select(*(h[0] for h in histories), now=time.monotonic())
            if pair:
                images = depth.rectify(*(f.image for f in pair))
                timestamp = min(f.t_mono for f in pair)
                skew_ms = abs(pair[0].t_mono-pair[1].t_mono)*1000
                for i, (view, frame, image) in enumerate(zip(views, pair, images)):
                    view.frame = Frame(image, frame.index, frame.t_mono)
                    view.status, view.tracks = "LIVE", []
                    if last_pair:
                        view.fps = 1/max(.001, now-last_pair)
                    counts[i] += 1
                last_pair = now
                tracks = detector.track(images[0])
                primary = (next((t for t in tracks if t.track_id == locked_id), None)
                           if locked_id is not None else select_primary(tracks))
                stereo["valid"] = False
                stereo["status"] = "NO PERSON IN LEFT VIEW"
                if primary is not None:
                    views[0].tracks = [primary]
                    disparity = depth.disparity(*images)
                    fix = depth.person_fix(disparity, primary)
                    stereo["status"] = "WAITING FOR RELIABLE STEREO MATCH"
                    if fix is not None and time.monotonic()-timestamp <= target.stale_s:
                        xyz = alignment.to_room(fix.xyz_left) if alignment else rig_to_room(fix.xyz_left, poses[0])
                        if np.isfinite(xyz[:2]).all() and target.observe(float(xyz[0]), float(xyz[1]), primary.track_id, timestamp):
                            measurements += 1
                            stereo.update(valid=True, status=f"STEREO VALID / HOST SKEW {skew_ms:.0f} ms",
                                          detail=f"Depth {fix.xyz_left[2]:.2f} m / support {fix.valid_fraction:.0%}",
                                          depth_m=float(fix.xyz_left[2]), support_fraction=fix.valid_fraction,
                                          skew_ms=skew_ms)
                            views[1].tracks = [Track(primary.track_id, *fix.right_box, primary.conf)]
                            for view in views:
                                view.target.track_id = primary.track_id
                            if rows:
                                rows.writerow([f"{now-start:.3f}", "stereo", primary.track_id,
                                               f"{xyz[0]:.3f}", f"{xyz[1]:.3f}",
                                               f"{xyz[2]:.3f}" if alignment else "",
                                               f"{fix.xyz_left[2]:.3f}", f"{skew_ms:.1f}", fix.samples,
                                               f"{fix.depth_spread_m:.3f}", "measured floor" if alignment else "assumed level rig"])
                if not stereo["valid"]:
                    stereo["detail"] = ""
            elif last_pair is None or now-last_pair > .8:
                stereo.update(valid=False, status="NEED FRESH LEFT + RIGHT CAMERA PAIR")
            points, radar_status = [], "NOT CONNECTED"
            if radar:
                points, rn, error, age = radar.snapshot(time.monotonic())
                radar_status = ("ERROR / CHECK PORT" if error not in ("", "opening", "waiting for reports") else
                                "WAITING FOR REPORTS" if rn == 0 else "STALE" if age > .8 else f"LIVE / {len(points)} TARGETS")
                if rows and rn != radar_frames and age <= .8:
                    for i, (x, y) in enumerate(points):
                        rows.writerow([f"{now-start:.3f}", "radar", i, f"{x:.3f}", f"{y:.3f}", "", "", "", "", "", "configured radar pose"])
                radar_frames = rn
            stereo["elapsed_s"] = time.monotonic()-start
            stereo["locked"] = locked_id is not None
            overlay = render(views, now=time.monotonic(), room=room, stereo=stereo,
                             radar_points=points, radar_status=radar_status, recording=writer is not None,
                             size=render_size(None if args.headless else window,
                                              forced_width=args.dashboard_width,
                                              record_size=record_size if writer else None))
            if writer:
                encoded = recording_frame(overlay, record_size)
                record_time = time.monotonic()
                while next_record <= record_time:
                    writer.write(encoded)
                    next_record += 1/15
                if now-last_flush > 1:
                    csv_file.flush()
                    last_flush = now
            if not args.headless:
                cv2.imshow(window, overlay)
                key = cv2.waitKey(10) & 0xff
                if ord("A") <= key <= ord("Z"):
                    key += 32
                if key == ord("q"):
                    break
                if key == ord("c"):
                    target.trail.clear()
                if key == ord("d"):
                    stereo["show_details"] = not stereo["show_details"]
                    stereo["show_cameras"] = False
                if key == ord("v"):
                    stereo["show_cameras"] = not stereo.get("show_cameras", False)
                    stereo["show_details"] = False
                if key == ord("f"):
                    fullscreen = not fullscreen
                    cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
                if key == ord("l"):
                    locked_id = None if locked_id is not None else (primary.track_id if primary else None)
                    target.clear()
                    stereo["valid"] = False
            else:
                time.sleep(.01)
            if args.seconds and now-start >= args.seconds:
                break
            if last_pair is None and now-start > 20:
                raise StereoError(f"No accepted camera pairs. Statuses: {[h[1] for h in histories]}. Check both webcams and receipt skew.")
        print(f"Accepted paired frames: {counts[0]}; valid stereo person measurements: {measurements}")
        if args.record:
            print(f"Recording: {args.record.resolve()}")
        if not measurements:
            print("No valid stereo person depth was measured. This recording does not establish depth accuracy.")
        return 0 if measurements else 2
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
