"""Click 4+ floor points to calibrate the fixed room camera's floor-plane homography.

    python -m kogane_base.vision.calibrate --source webcam --camera 0
    python -m kogane_base.vision.calibrate --source video --path clip.mp4 --out calib/floor.json

Workflow: tape-measure a rectangle on the floor and note each corner's room coordinates.
Click the corners in the frame, then type the room x,y for each. 4 corners of a rectangle
is the easy case, but any 4+ non-collinear floor points work.

Non-interactive alternative, if you already have the numbers:

    python -m kogane_base.vision.calibrate --points "100,400=0,0; 540,400=3,0; 600,300=3,4; 40,300=0,4"

Once saved, turn it on with KGN_USE_FLOOR_HOMOGRAPHY=1 and KGN_FLOOR_CALIB=<path>.
"""
from __future__ import annotations

import argparse
import math
import sys

from ..config import CONFIG
from .geometry import FloorHomography


def _parse_points(spec: str):
    """'u,v=x,y; u,v=x,y; ...' -> (image_pts, room_pts)."""
    img_pts, room_pts = [], []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"expected 'u,v=x,y', got {chunk!r}")
        left, right = chunk.split("=", 1)
        u, v = (float(t) for t in left.split(","))
        x, y = (float(t) for t in right.split(","))
        img_pts.append((u, v))
        room_pts.append((x, y))
    return img_pts, room_pts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Calibrate the room camera's floor homography")
    p.add_argument("--source", choices=["webcam", "video", "mjpeg", "usb"], default="webcam")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--capture-width", type=int, help="match the mapping camera capture width")
    p.add_argument("--capture-height", type=int, help="match the mapping camera capture height")
    p.add_argument("--capture-fps", type=float, default=15)
    p.add_argument("--camera-api", choices=["auto", "dshow", "msmf"], default="auto")
    p.add_argument("--path", help="video file path (--source video)")
    p.add_argument("--url", help="MJPEG stream URL (--source mjpeg)")
    p.add_argument("--out", default=CONFIG.floor_calib_path, help="where to save the JSON")
    p.add_argument("--points", help="non-interactive: 'u,v=x,y; u,v=x,y; ...'")
    p.add_argument("--note", default="", help="free-text note stored in the calibration")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.points:
        img_pts, room_pts = _parse_points(args.points)
        hom = FloorHomography.from_points(img_pts, room_pts, note=args.note)
        hom.save(args.out)
        print(f"saved {args.out}  (reprojection error {hom.reprojection_error_m():.3f} m)")
        return

    import cv2

    from .sources import FrameSource, make_source

    value = {"webcam": str(args.camera), "usb": str(args.camera),
             "video": args.path, "mjpeg": args.url}[args.source]
    if args.source in ("webcam", "usb") and (
            args.capture_width is not None or args.capture_height is not None or args.camera_api != "auto"):
        width = args.capture_width if args.capture_width is not None else 640
        height = args.capture_height if args.capture_height is not None else 480
        if width <= 0 or height <= 0 or not math.isfinite(args.capture_fps) or args.capture_fps <= 0:
            raise ValueError("Camera capture dimensions and FPS must be positive.")
        backend = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}[args.camera_api]
        src = FrameSource(args.camera, backend)
        src.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        src.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        src.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        src.cap.set(cv2.CAP_PROP_FPS, args.capture_fps)
    else:
        src = make_source(args.source, value)
    try:
        frame = next(iter(src))
    except StopIteration:
        print("no frames from source", file=sys.stderr)
        raise SystemExit(2)
    finally:
        src.release()

    img = frame.image
    h, w = img.shape[:2]
    clicks: list[tuple[float, float]] = []

    def on_click(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((float(x), float(y)))
            print(f"point {len(clicks)}: pixel ({x}, {y})")

    win = "floor calibration - click floor points, ENTER when done, r=reset, q=quit"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    print("Click at least 4 points that lie flat on the floor, then press ENTER.")

    while True:
        canvas = img.copy()
        for i, (u, v) in enumerate(clicks):
            cv2.circle(canvas, (int(u), int(v)), 6, (0, 0, 255), -1)
            cv2.putText(canvas, str(i + 1), (int(u) + 8, int(v) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.putText(canvas, f"{len(clicks)} point(s) - ENTER to finish, r reset, q quit",
                    (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10):
            if len(clicks) >= 4:
                break
            print(f"need >=4 points, have {len(clicks)}")
        elif key == ord("r"):
            clicks.clear()
            print("reset")
        elif key == ord("q"):
            cv2.destroyAllWindows()
            return
    cv2.destroyAllWindows()

    room_pts = []
    print("\nNow the room coordinates, in metres, same order you clicked:")
    for i, (u, v) in enumerate(clicks):
        while True:
            raw = input(f"  point {i + 1} at pixel ({u:.0f}, {v:.0f}) -> room x,y : ")
            try:
                x, y = (float(t) for t in raw.replace(" ", "").split(","))
                room_pts.append((x, y))
                break
            except ValueError:
                print("    expected two numbers like 1.5,2.0")

    hom = FloorHomography.from_points(clicks, room_pts, img_size=(w, h), note=args.note)
    err = hom.reprojection_error_m()
    hom.save(args.out)
    print(f"\nsaved {args.out}")
    print(f"mean reprojection error: {err:.3f} m "
          f"({'good' if err < 0.1 else 'high - re-check your measurements'})")
    print("enable it with:  set KGN_USE_FLOOR_HOMOGRAPHY=1")


if __name__ == "__main__":
    main()
