"""Turn a person's bounding box into a room-frame position.

Two independent methods live here, and picking between them is an explicit decision
made by the caller (see `RoomProjector`), never an implicit fallback:

`MonocularEstimator` — pinhole + assumed person height.
    Needs no calibration at all, so it is the only option for the *drone's own camera*,
    which moves and can never have a fixed floor calibration. Accuracy on distance is
    rough (±20-40%); bearing is reliable. Use this on the drone, and as the bootstrap
    path for a room camera that has not been calibrated yet.

`FloorHomography` — 4+ clicked floor points -> cv2.findHomography.
    For a *fixed room camera* only. Maps the bottom-center ("foot") pixel of a box
    straight onto the floor plane, which is far more accurate than inferring range
    from apparent height, and is immune to people being short/tall or partially
    cropped at the top. Requires the person's feet to be visible and the camera to
    not move. Calibration persists as JSON so it survives restarts.

Both end up producing metres in the shared room frame, the same frame
`tracking.mmwave.node_frame_to_room` produces, so everything can be fused.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class CameraEstimate:
    bearing_deg: float      # +right of center
    distance_m: float       # forward range estimate
    x_m: float              # camera frame: +right (lateral)
    y_m: float              # camera frame: +forward
    conf: float


class MonocularEstimator:
    def __init__(self, img_w: int, img_h: int,
                 hfov_deg: float = 70.0,
                 assumed_person_height_m: float = 1.7) -> None:
        self.img_w = img_w
        self.img_h = img_h
        self.hfov = math.radians(hfov_deg)
        self.person_h = assumed_person_height_m
        # focal length in pixels from horizontal FOV
        self.fx = (img_w / 2.0) / math.tan(self.hfov / 2.0)
        # assume square pixels; vertical focal length == horizontal
        self.fy = self.fx

    def estimate(self, x1: float, y1: float, x2: float, y2: float, conf: float = 1.0) -> CameraEstimate:
        cx = (x1 + x2) / 2.0
        box_h = max(1.0, y2 - y1)

        # horizontal bearing from pixel offset
        dx = cx - self.img_w / 2.0
        bearing = math.atan2(dx, self.fx)

        # distance from apparent height: box_h_px = fy * real_h / distance
        distance = self.fy * self.person_h / box_h

        x = distance * math.sin(bearing)     # lateral (+right)
        y = distance * math.cos(bearing)     # forward
        return CameraEstimate(math.degrees(bearing), distance, x, y, conf)


def project_to_room(est: CameraEstimate, cam_pose: tuple[float, float, float]) -> tuple[float, float]:
    """Rotate/translate a camera-frame estimate into the shared room frame.

    cam_pose = (cam_x_m, cam_y_m, cam_yaw_deg). Mirrors tracking.mmwave.node_frame_to_room
    so camera + mmWave land in the same coordinate system and can be fused.

    Note: this is for `MonocularEstimator` output. `FloorHomography` already returns
    room-frame coordinates directly (the calibration points were given in room
    coordinates), so its output must NOT be passed through here.
    """
    ox, oy, yaw_deg = cam_pose
    a = math.radians(yaw_deg)
    rx = ox + est.x_m * math.cos(a) - est.y_m * math.sin(a)
    ry = oy + est.x_m * math.sin(a) + est.y_m * math.cos(a)
    return rx, ry


# --------------------------------------------------------------------------------------
# Floor-plane homography (fixed room camera)
# --------------------------------------------------------------------------------------

class FloorHomographyError(RuntimeError):
    """Raised for bad calibration input or a missing/corrupt calibration file."""


@dataclass
class FloorFix:
    """A room-frame position obtained by projecting a pixel onto the floor plane."""
    x_m: float
    y_m: float
    conf: float = 1.0


class FloorHomography:
    """Maps floor pixels to room-frame metres via a 3x3 planar homography.

    Calibrate once, from at least 4 non-collinear points that lie on the floor and
    whose room coordinates you know (tape-measure the corners of a rectangle, or use
    known floor-tile intersections). Then `image_to_room` sends any floor pixel to
    metres, and `track_to_room` does it for a detection's foot point.

    The homography is only valid for points ON the floor plane. Feeding it a pixel in
    mid-air (e.g. a person's head) gives a meaningless answer, which is exactly why
    `track_to_room` uses `Track.foot`.
    """

    def __init__(self, H, img_size: tuple[int, int] | None = None,
                 image_pts=None, room_pts=None, note: str = "") -> None:
        H = np.asarray(H, dtype=np.float64)
        if H.shape != (3, 3):
            raise FloorHomographyError(f"homography must be 3x3, got {H.shape}")
        if not np.isfinite(H).all():
            raise FloorHomographyError("homography contains non-finite values")
        if abs(float(np.linalg.det(H))) < 1e-12:
            raise FloorHomographyError("homography is singular (degenerate calibration points?)")
        self.H = H
        self._Hinv = np.linalg.inv(H)
        self.img_size = img_size
        self.image_pts = None if image_pts is None else np.asarray(image_pts, dtype=np.float64)
        self.room_pts = None if room_pts is None else np.asarray(room_pts, dtype=np.float64)
        self.note = note

    # ---- construction ----
    @classmethod
    def from_points(cls, image_pts, room_pts, img_size: tuple[int, int] | None = None,
                    note: str = "", ransac_reproj_px: float = 3.0) -> "FloorHomography":
        """Fit image->room from >=4 corresponding points.

        image_pts: [(u_px, v_px), ...]   room_pts: [(x_m, y_m), ...]
        With exactly 4 pairs an exact solve is used; with more, RANSAC rejects outliers
        from sloppy clicking.
        """
        import cv2  # local import so the base package works without the vision extra

        src = np.asarray(image_pts, dtype=np.float64).reshape(-1, 2)
        dst = np.asarray(room_pts, dtype=np.float64).reshape(-1, 2)
        if src.shape[0] != dst.shape[0]:
            raise FloorHomographyError(
                f"point count mismatch: {src.shape[0]} image vs {dst.shape[0]} room")
        if src.shape[0] < 4:
            raise FloorHomographyError(f"need at least 4 point pairs, got {src.shape[0]}")

        if src.shape[0] == 4:
            H, _mask = cv2.findHomography(src, dst, 0)
        else:
            H, _mask = cv2.findHomography(src, dst, cv2.RANSAC, ransac_reproj_px)
        if H is None:
            raise FloorHomographyError(
                "cv2.findHomography failed — calibration points are probably collinear "
                "or duplicated")
        return cls(H, img_size=img_size, image_pts=src, room_pts=dst, note=note)

    # ---- mapping ----
    def image_to_room(self, u: float, v: float) -> tuple[float, float]:
        """Project one floor pixel to room-frame metres."""
        p = self.H @ np.array([float(u), float(v), 1.0])
        w = p[2]
        if abs(w) < 1e-12:
            raise FloorHomographyError(
                f"pixel ({u}, {v}) maps to the horizon (w~0) — it is not on the floor plane")
        return float(p[0] / w), float(p[1] / w)

    def room_to_image(self, x_m: float, y_m: float) -> tuple[float, float]:
        """Inverse map, handy for drawing a room grid back onto the frame."""
        p = self._Hinv @ np.array([float(x_m), float(y_m), 1.0])
        w = p[2]
        if abs(w) < 1e-12:
            raise FloorHomographyError(f"room point ({x_m}, {y_m}) is not imageable")
        return float(p[0] / w), float(p[1] / w)

    def track_to_room(self, track, conf: float | None = None) -> FloorFix:
        """Project a detection's foot (bottom-center) pixel onto the floor.

        Works with `detector.Track` or anything exposing a `.foot` (u, v) pair.
        """
        u, v = track.foot
        x, y = self.image_to_room(u, v)
        c = track.conf if conf is None else conf
        return FloorFix(x, y, float(c))

    # ---- quality ----
    def reprojection_error_m(self) -> float | None:
        """Mean calibration-point error in metres, or None if points weren't kept.

        A good hand calibration lands well under 0.10 m. Much more than that and you
        probably mis-measured a room point or clicked the wrong pixel.
        """
        if self.image_pts is None or self.room_pts is None:
            return None
        errs = []
        for (u, v), (x, y) in zip(self.image_pts, self.room_pts):
            px, py = self.image_to_room(u, v)
            errs.append(math.hypot(px - x, py - y))
        return float(np.mean(errs)) if errs else None

    # ---- persistence ----
    def to_dict(self) -> dict:
        d: dict = {
            "type": "kogane.floor_homography",
            "version": 1,
            "H": self.H.tolist(),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": self.note,
        }
        if self.img_size is not None:
            d["img_size"] = [int(self.img_size[0]), int(self.img_size[1])]
        if self.image_pts is not None:
            d["image_pts"] = self.image_pts.tolist()
        if self.room_pts is not None:
            d["room_pts"] = self.room_pts.tolist()
        err = self.reprojection_error_m()
        if err is not None:
            d["reprojection_error_m"] = err
        return d

    def save(self, path: str) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "FloorHomography":
        if "H" not in d:
            raise FloorHomographyError("calibration dict has no 'H' key")
        size = d.get("img_size")
        return cls(
            d["H"],
            img_size=(int(size[0]), int(size[1])) if size else None,
            image_pts=d.get("image_pts"),
            room_pts=d.get("room_pts"),
            note=d.get("note", ""),
        )

    @classmethod
    def load(cls, path: str) -> "FloorHomography":
        if not os.path.exists(path):
            raise FloorHomographyError(
                f"no floor calibration at {path!r}. Create one with "
                f"FloorHomography.from_points(image_pts, room_pts).save(path), or run "
                f"`python -m kogane_base.vision.calibrate --source webcam` to click 4 "
                f"floor points.")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except (OSError, json.JSONDecodeError) as e:
            raise FloorHomographyError(f"could not read calibration {path!r}: {e}") from e


# --------------------------------------------------------------------------------------
# Explicit method selection
# --------------------------------------------------------------------------------------

@dataclass
class RoomFix:
    """A room-frame target position plus provenance, so logs say how it was derived."""
    x_m: float
    y_m: float
    conf: float
    method: str                     # "homography" | "monocular"
    distance_m: float | None = None  # monocular only
    bearing_deg: float | None = None  # monocular only


class RoomProjector:
    """One interface over the two projection methods, chosen explicitly at construction.

    Use `from_homography` for the fixed room camera once it is calibrated; use
    `from_monocular` for the drone's own camera, or for a room camera before you have
    had a chance to calibrate it. `method` records which one is live.
    """

    def __init__(self, homography: FloorHomography | None = None,
                 monocular: MonocularEstimator | None = None,
                 cam_pose: tuple[float, float, float] = (0.0, 0.0, 90.0)) -> None:
        if homography is None and monocular is None:
            raise ValueError("RoomProjector needs a FloorHomography or a MonocularEstimator")
        self.homography = homography
        self.monocular = monocular
        self.cam_pose = cam_pose

    @classmethod
    def from_homography(cls, hom: FloorHomography) -> "RoomProjector":
        return cls(homography=hom)

    @classmethod
    def from_monocular(cls, est: MonocularEstimator,
                       cam_pose: tuple[float, float, float]) -> "RoomProjector":
        return cls(monocular=est, cam_pose=cam_pose)

    @property
    def method(self) -> str:
        return "homography" if self.homography is not None else "monocular"

    def locate(self, track) -> RoomFix:
        """Room-frame position for one track, using whichever method is configured."""
        if self.homography is not None:
            fix = self.homography.track_to_room(track)
            return RoomFix(fix.x_m, fix.y_m, fix.conf, "homography")
        est = self.monocular.estimate(track.x1, track.y1, track.x2, track.y2, track.conf)
        rx, ry = project_to_room(est, self.cam_pose)
        return RoomFix(rx, ry, est.conf, "monocular",
                       distance_m=est.distance_m, bearing_deg=est.bearing_deg)
