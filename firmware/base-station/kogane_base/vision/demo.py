"""Standalone CV test: person detection + tracking, optional pose and FaceID.

Examples
--------
    kogane-cv                                   # webcam 0, live window
    python -m kogane_base.vision.demo --source webcam --camera 0
    python -m kogane_base.vision.demo --source video --path clip.mp4
    python -m kogane_base.vision.demo --source mjpeg --url http://192.168.4.2/stream
    python -m kogane_base.vision.demo --fuse     # also run the Kalman filter on the target
    python -m kogane_base.vision.demo --headless # no window (prints target position)

    python -m kogane_base.vision.demo --pose                  # + skeleton and gesture read
    python -m kogane_base.vision.demo --faceid                # + name known faces
    python -m kogane_base.vision.demo --faceid --enroll sujay # press 'e' to enroll a face
    python -m kogane_base.vision.demo --faceid --list-faces   # who is enrolled, then exit
    python -m kogane_base.vision.demo --homography calib/floor.json   # room-frame metres

Keys in the window:
    q  quit
    l  lock/unlock onto the current primary target
    e  enroll the largest face under --enroll NAME (FaceID mode)

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
    from ..config import CONFIG

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

    p.add_argument("--pose", action="store_true",
                   help="also run yolov8n-pose and read arm-raise gestures")
    p.add_argument("--pose-model", default=CONFIG.pose_model_path)
    p.add_argument("--faceid", action="store_true",
                   help="also run YuNet+SFace face recognition")
    p.add_argument("--face-db", default=CONFIG.face_db_path)
    p.add_argument("--face-threshold", type=float, default=CONFIG.face_match_threshold,
                   help="cosine similarity needed to call a face known")
    p.add_argument("--face-every-n", type=int, default=CONFIG.face_every_n_frames,
                   help="run the FaceID pass every Nth frame")
    p.add_argument("--enroll", metavar="NAME",
                   help="press 'e' to add the largest visible face to the DB as NAME")
    p.add_argument("--list-faces", action="store_true", help="print enrolled names and exit")
    p.add_argument("--homography", metavar="JSON",
                   help="use a calibrated floor homography instead of height-based distance")
    p.add_argument("--face-lock", action="store_true",
                   help="let a recognised face take over the primary-target lock")
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

    from ..config import CONFIG
    from .geometry import FloorHomography, MonocularEstimator, RoomProjector
    from .sources import make_source

    # ---- FaceID setup (can exit early for --list-faces) ----
    faceid = None
    if args.faceid or args.list_faces:
        from .faceid import FaceIdentifier, assign_face_to_track, resolve_locked_id

        try:
            faceid = FaceIdentifier(
                CONFIG.face_detect_model, CONFIG.face_recog_model, args.face_db,
                threshold=args.face_threshold,
                score_threshold=CONFIG.face_score_threshold)
        except Exception as e:
            print(f"[kogane-cv] FaceID unavailable: {e}", file=sys.stderr)
            raise SystemExit(2)
        print(f"[kogane-cv] face DB {args.face_db}: "
              f"{faceid.db.names if faceid.db.names else '(nobody enrolled)'}")
        if args.list_faces:
            for name in faceid.db.names:
                print(f"  {name}: {len(faceid.db.people[name])} embedding(s)")
            return

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

    # ---- explicit choice of room-frame projection ----
    if args.homography:
        hom = FloorHomography.load(args.homography)
        projector = RoomProjector.from_homography(hom)
        err = hom.reprojection_error_m()
        print(f"[kogane-cv] floor homography from {args.homography}"
              f"{'' if err is None else f' (reprojection error {err:.3f} m)'}")
    else:
        projector = RoomProjector.from_monocular(
            MonocularEstimator(w, h, hfov_deg=args.hfov,
                               assumed_person_height_m=args.person_height),
            tuple(CONFIG.cam_pose))
        print("[kogane-cv] monocular height-based distance "
              "(pass --homography for a calibrated room camera)")

    pose = None
    beckon = None
    if args.pose:
        from .pose import BeckonDetector, PoseEstimator, classify_gesture
        from .pose import draw_pose, match_pose_to_track

        print(f"[kogane-cv] loading pose model {args.pose_model} ...")
        pose = PoseEstimator(args.pose_model, device=args.device, conf=args.conf)
        beckon = BeckonDetector()

    kf = None
    if args.fuse:
        from ..fusion.kalman import PositionFilter
        kf = PositionFilter()

    locked_id: int | None = None
    locked_name: str | None = None
    ema_fps = 0.0
    last = time.monotonic()
    faces: list = []
    banner = ""
    banner_until = 0.0
    beckon_until = 0.0

    try:
        for frame in frames:
            tracks = detector.track(frame.image)

            now = time.monotonic()
            dt = max(1e-3, now - last)
            last = now
            ema_fps = 0.9 * ema_fps + 0.1 * (1.0 / dt) if ema_fps else 1.0 / dt

            # ---- FaceID pass ----
            if faceid is not None and frame.index % max(1, args.face_every_n) == 0:
                try:
                    faces = faceid.identify_frame(frame.image)
                except Exception as e:
                    print(f"[kogane-cv] FaceID pass failed: {e}", file=sys.stderr)
                    faces = []
                if args.face_lock:
                    new_id = resolve_locked_id(faces, tracks)
                    if new_id is not None and new_id != locked_id:
                        locked_id = new_id
                        named = [f.ident.name for f in faces if f.ident.known]
                        locked_name = named[0] if named else None
                        banner = f"FaceID lock -> #{locked_id} {locked_name}"
                        banner_until = now + 2.0
                        print(f"[kogane-cv] {banner}")

            primary = select_primary(tracks, locked_id)

            # ---- name every track we can, for the on-screen labels ----
            names: dict[int, str] = {}
            if faceid is not None:
                for f in faces:
                    if f.ident.known:
                        t = assign_face_to_track(f.box, tracks)
                        if t is not None:
                            names[t.track_id] = f.ident.name

            # ---- pose pass on the primary target ----
            gesture_label = "-"
            poses: list = []
            if pose is not None:
                try:
                    poses = pose.estimate(frame.image)
                except Exception as e:
                    print(f"[kogane-cv] pose pass failed: {e}", file=sys.stderr)
                    poses = []
                raised = False
                if primary is not None:
                    matched = match_pose_to_track(primary, poses)
                    if matched is not None:
                        g = classify_gesture(matched.keypoints)
                        gesture_label = g.label
                        raised = g.any_arm_raised
                if beckon.update(raised):
                    beckon_until = now + 2.5
                    print("[kogane-cv] *** COME HERE *** (beckon gesture)")

            target_txt = "no target"
            if primary is not None:
                fix = projector.locate(primary)
                if kf is not None:
                    kf.predict(dt)
                    kf.update(fix.x_m, fix.y_m)
                    px, py = kf.position
                    pos_txt = f"KF=({px:+.2f},{py:+.2f})m"
                else:
                    pos_txt = f"room=({fix.x_m:+.2f},{fix.y_m:+.2f})m"
                dist_txt = ("dist~%.1fm" % fix.distance_m) if fix.distance_m is not None else ""
                name_txt = names.get(primary.track_id, locked_name or "")
                target_txt = (f"id={primary.track_id}"
                              f"{' ' + name_txt if name_txt else ''} "
                              f"[{fix.method}] {dist_txt} {pos_txt} gesture={gesture_label}")

            if args.headless:
                if frame.index % 15 == 0:
                    print(f"[{ema_fps:4.1f} fps] {target_txt}")
            else:
                _draw(cv2, frame.image, tracks, primary, ema_fps, target_txt, locked_id,
                      names, faces, poses, projector,
                      banner if now < banner_until else "",
                      now < beckon_until)
                if pose is not None and poses:
                    for p in poses:
                        draw_pose(cv2, frame.image, p.keypoints)
                cv2.imshow("kogane-cv (q quit, l lock, e enroll)", frame.image)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("l"):
                    locked_id = None if locked_id is not None else (
                        primary.track_id if primary else None)
                    locked_name = names.get(locked_id) if locked_id is not None else None
                    print(f"[kogane-cv] locked_id -> {locked_id}")
                if key == ord("e") and faceid is not None:
                    if not args.enroll:
                        print("[kogane-cv] pass --enroll NAME to enroll a face")
                    else:
                        obs = faceid.enroll_frame(frame.image, args.enroll)
                        if obs is None:
                            print("[kogane-cv] no face found to enroll")
                            banner = "enroll: no face found"
                        else:
                            n = len(faceid.db.people[args.enroll])
                            print(f"[kogane-cv] enrolled {args.enroll} ({n} embedding(s))")
                            banner = f"enrolled {args.enroll} ({n})"
                        banner_until = now + 2.0
    finally:
        src.release()
        if not args.headless:
            import cv2 as _cv2
            _cv2.destroyAllWindows()


def _chain_first(first, src):
    yield first
    yield from src


def _draw(cv2, img, tracks, primary, fps, target_txt, locked_id,
          names=None, faces=(), poses=(), projector=None,
          banner="", beckoning=False) -> None:
    names = names or {}
    for t in tracks:
        is_primary = primary is not None and t is primary
        color = (0, 0, 255) if is_primary else (0, 200, 0)
        thick = 3 if is_primary else 1
        cv2.rectangle(img, (int(t.x1), int(t.y1)), (int(t.x2), int(t.y2)), color, thick)
        tag = f"#{t.track_id}"
        if t.track_id in names:
            tag += f" {names[t.track_id]}"
        if is_primary:
            tag += " *LOCK*" if locked_id is not None else " *primary*"
        _label(cv2, img, tag, int(t.x1), int(t.y1) - 6, color, 0.6)
        if is_primary and projector is not None:
            try:
                fix = projector.locate(t)
                sub = (f"{fix.distance_m:.1f}m" if fix.distance_m is not None
                       else f"({fix.x_m:+.1f},{fix.y_m:+.1f})m")
                _label(cv2, img, sub, int(t.x1), int(t.y2) + 18, color, 0.6)
            except Exception:
                pass

    for f in faces:
        fc = (0, 255, 0) if f.ident.known else (128, 128, 128)
        cv2.rectangle(img, (int(f.x1), int(f.y1)), (int(f.x2), int(f.y2)), fc, 2)
        _label(cv2, img, f.label, int(f.x1), int(f.y1) - 4, fc, 0.5)

    _label(cv2, img, f"{fps:4.1f} fps", 8, 24, (255, 255, 0), 0.7)
    _label(cv2, img, target_txt, 8, img.shape[0] - 14, (255, 255, 255), 0.6)
    if banner:
        _label(cv2, img, banner, 8, 52, (0, 255, 255), 0.7)
    if beckoning:
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), (0, 140, 255), 8)
        _label(cv2, img, "COME HERE", int(w * 0.30), int(h * 0.16), (0, 140, 255), 1.4)


def _label(cv2, img, text, x, y, color, scale) -> None:
    """Text with a dark outline so it stays readable over any background."""
    y = max(int(y), 14)
    cv2.putText(img, text, (int(x), y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                max(3, int(scale * 5)), cv2.LINE_AA)
    cv2.putText(img, text, (int(x), y), cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                max(1, int(scale * 2)), cv2.LINE_AA)


if __name__ == "__main__":
    main()
