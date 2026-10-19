"""Calibrated binocular depth with timing, correspondence and geometric checks.

Coordinates returned by depth are in the original left optical frame: x right,
y down, z forward, metres. Optional floor pose converts these into room x/y/z.
USB timestamps describe host receipt, not synchronized sensor exposure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path

import numpy as np


class StereoError(ValueError):
    pass


class PairSelector:
    def __init__(self, max_skew_s=.04, max_age_s=.5):
        if not (0 < max_skew_s <= .1 and 0 < max_age_s <= 1):
            raise StereoError("Stereo receipt skew must be 0–100 ms; frame age must be 0–1 s.")
        self.max_skew_s, self.max_age_s = max_skew_s, max_age_s
        self.used = (-1, -1)

    def select(self, left, right, now):
        left = [f for f in left if f.index > self.used[0] and 0 <= now-f.t_mono <= self.max_age_s]
        right = [f for f in right if f.index > self.used[1] and 0 <= now-f.t_mono <= self.max_age_s]
        pairs = [(a, b) for a in left for b in right
                 if abs(a.t_mono-b.t_mono) <= self.max_skew_s]
        if not pairs:
            return None
        a, b = max(pairs, key=lambda ab: (min(ab[0].t_mono, ab[1].t_mono),
                                         -abs(ab[0].t_mono-ab[1].t_mono)))
        self.used = a.index, b.index
        return a, b


@dataclass
class StereoCalibration:
    K1: np.ndarray
    D1: np.ndarray
    K2: np.ndarray
    D2: np.ndarray
    R: np.ndarray
    T: np.ndarray
    size: tuple[int, int]
    devices: tuple[int, int]
    rms_px: float = 0.0
    epipolar_px: float = 0.0
    quality_notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        for name in ("K1", "D1", "K2", "D2", "R", "T"):
            value = np.asarray(getattr(self, name), dtype=np.float64)
            if not np.isfinite(value).all():
                raise StereoError(f"Calibration {name} contains non-finite values.")
            setattr(self, name, value)
        self.T = self.T.reshape(3, 1)
        self.size, self.devices = tuple(self.size), tuple(self.devices)
        if any(getattr(self, name).shape != (3, 3) for name in ("K1", "K2", "R")):
            raise StereoError("Calibration matrix dimensions are invalid.")
        if not np.allclose(self.R.T @ self.R, np.eye(3), atol=1e-4) or np.linalg.det(self.R) < .99:
            raise StereoError("Calibration rotation is invalid.")
        if min(*self.size) <= 0 or len(self.size) != 2 or len(self.devices) != 2 or self.devices[0] == self.devices[1]:
            raise StereoError("Calibration image size / device pair is invalid.")
        if any(k[0, 0] <= 0 or k[1, 1] <= 0 for k in (self.K1, self.K2)):
            raise StereoError("Calibration focal length is invalid.")
        if not .01 < self.baseline_m < 2:
            raise StereoError("Calibration baseline is outside 1 cm–2 m; check square-size units.")
        if not (math.isfinite(self.rms_px) and 0 <= self.rms_px <= 1.5 and
                math.isfinite(self.epipolar_px) and 0 <= self.epipolar_px <= 1):
            raise StereoError("Stereo calibration exceeds quality limits (RMS 1.5 px, median vertical error 1 px).")

    @property
    def baseline_m(self):
        return float(np.linalg.norm(self.T))

    def validate_capture(self, devices, size, expected_baseline):
        if tuple(devices) != self.devices:
            raise StereoError(f"Calibration is for left/right devices {self.devices}, not {tuple(devices)}. Verify physical lenses/order and recalibrate if needed.")
        if tuple(size) != self.size:
            raise StereoError(f"Calibrated image size {self.size} differs from capture {tuple(size)}; use matching settings or recalibrate.")
        if not math.isfinite(expected_baseline) or expected_baseline <= 0:
            raise StereoError("Measured lens spacing must be positive metres.")
        if abs(self.baseline_m-expected_baseline) > max(.02, .15*expected_baseline):
            raise StereoError(f"Calibrated spacing {self.baseline_m:.3f} m disagrees with measured {expected_baseline:.3f} m; check tablet square size and repeat calibration.")

    def rectification(self):
        import cv2
        return cv2.stereoRectify(self.K1, self.D1, self.K2, self.D2, self.size,
                                self.R, self.T, flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: getattr(self, name).tolist() for name in ("K1", "D1", "K2", "D2", "R", "T")}
        data.update(type="kogane.stereo", version=1, size=self.size, devices=self.devices,
                    rms_px=self.rms_px, epipolar_px=self.epipolar_px,
                    baseline_m=self.baseline_m, quality_notes=self.quality_notes)
        temporary = path.with_suffix(path.suffix+".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.is_file():
            raise StereoError(f"Stereo calibration missing: {path}. Run python -m kogane_base.vision.stereo_calibrate first. Camera spacing alone cannot calibrate stereo.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("type") != "kogane.stereo" or data.get("version") != 1:
            raise StereoError("This file is not a stereo calibration. Separate floor homographies cannot replace it.")
        return cls(**{name: data[name] for name in ("K1", "D1", "K2", "D2", "R", "T", "size", "devices", "rms_px", "epipolar_px")},
                   quality_notes=data.get("quality_notes", []))


@dataclass
class DepthFix:
    xyz_left: np.ndarray
    samples: int
    valid_fraction: float
    depth_spread_m: float
    right_box: tuple


class StereoDepth:
    def __init__(self, calibration, num_disparities=0, min_depth=.7, max_depth=6):
        import cv2
        self.calibration = calibration
        if not (0 < min_depth < max_depth and math.isfinite(max_depth)):
            raise StereoError("Stereo depth limits must be finite positive metres.")
        self.min_depth, self.max_depth = min_depth, max_depth
        self.R1, self.R2, self.P1, self.P2, self.Q, *_ = calibration.rectification()
        if num_disparities == 0:
            maximum = ((calibration.size[0]//2-1)//16)*16
            required = math.ceil(abs(self.P2[0, 3])/min_depth/16)*16
            num_disparities = min(maximum, max(16, required))
        if num_disparities <= 0 or num_disparities % 16 or num_disparities >= calibration.size[0]//2:
            raise StereoError("Disparity count must be a positive multiple of 16, smaller than half the image width; 0 selects automatically.")
        self.num_disparities = num_disparities
        self.nominal_near_m = abs(float(self.P2[0, 3]))/num_disparities
        if self.P2[0, 3] >= 0 or abs(self.P2[1, 3]) > abs(self.P2[0, 3])*.1:
            raise StereoError("This rig needs a horizontal left/right baseline with the right camera physically on the right. Check camera order and recalibrate.")
        self.maps = [cv2.initUndistortRectifyMap(k, d, r, p, calibration.size, cv2.CV_32FC1)
                     for k, d, r, p in ((calibration.K1, calibration.D1, self.R1, self.P1),
                                       (calibration.K2, calibration.D2, self.R2, self.P2))]
        opts = dict(numDisparities=num_disparities, blockSize=5, P1=8*25, P2=32*25,
                    disp12MaxDiff=1, preFilterCap=31, uniquenessRatio=12,
                    speckleWindowSize=80, speckleRange=2, mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)
        self.left_matcher = cv2.StereoSGBM_create(minDisparity=0, **opts)
        self.right_matcher = cv2.StereoSGBM_create(minDisparity=-num_disparities, **opts)

    def rectify(self, left, right):
        import cv2
        for img in (left, right):
            if (img.shape[1], img.shape[0]) != self.calibration.size:
                raise StereoError("Live image resolution differs from stereo calibration; refusing depth.")
        return tuple(cv2.remap(img, *maps, cv2.INTER_LINEAR) for img, maps in zip((left, right), self.maps))

    def disparity(self, left, right):
        import cv2
        gray_l, gray_r = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) for img in (left, right))
        dl = self.left_matcher.compute(gray_l, gray_r).astype(np.float32)/16
        dr = self.right_matcher.compute(gray_r, gray_l).astype(np.float32)/16
        yy, xx = np.indices(dl.shape)
        xr = np.rint(xx-dl).astype(int)
        valid = (dl > 1) & (xr >= 0) & (xr < dl.shape[1])
        opposite = dr[yy, np.clip(xr, 0, dl.shape[1]-1)]
        valid &= (opposite < -1) & (np.abs(dl+opposite) <= 1.5)
        gray = gray_l.astype(np.float32)
        variance = cv2.boxFilter(gray*gray, -1, (7, 7))-cv2.boxFilter(gray, -1, (7, 7))**2
        valid &= variance > 16  # blank regions cannot establish trustworthy correspondence
        return np.where(valid, dl, np.nan)

    def person_fix(self, disparity, track):
        """Robust textured torso surface; never triangulate two unrelated bbox centres."""
        hh, ww = disparity.shape
        x1 = max(0, int(track.x1+track.width*.3))
        x2 = min(ww, int(track.x1+track.width*.7))
        y1 = max(0, int(track.y1+track.height*.2))
        y2 = min(hh, int(track.y1+track.height*.65))
        if x2-x1 < 8 or y2-y1 < 8:
            return None
        patch = disparity[y1:y2, x1:x2]
        yy, xx = np.where(np.isfinite(patch))
        if len(xx) < 60 or len(xx)/patch.size < .08:
            return None
        d = patch[yy, xx]
        u, v = xx+x1, yy+y1
        points = np.column_stack((u, v, d, np.ones(len(d)))) @ self.Q.T
        valid_w = np.abs(points[:, 3]) > 1e-9
        xyz = np.full((len(d), 3), np.nan)
        xyz[valid_w] = points[valid_w, :3]/points[valid_w, 3:4]
        depth = xyz[:, 2]
        valid = np.isfinite(xyz).all(axis=1) & (depth >= self.min_depth) & (depth <= self.max_depth)
        if valid.sum() < 60:
            return None
        median = np.median(depth[valid])
        mad = np.median(np.abs(depth[valid]-median))
        if mad > max(.12, median*.08):
            return None
        valid &= np.abs(depth-median) <= max(.10, 3*mad)
        fraction = valid.sum()/patch.size
        if valid.sum() < 60 or fraction < .08:
            return None
        # Q reconstructs the rectified left frame; undo R1 before room projection.
        xyz_left = np.median(xyz[valid], axis=0) @ self.R1
        xr, vr = u[valid]-d[valid], v[valid]
        return DepthFix(xyz_left, int(valid.sum()), float(fraction), float(mad*1.4826),
                        (float(xr.min()), float(vr.min()), float(xr.max()), float(vr.max())))


class RoomAlignment:
    """Rigid room-to-left-camera pose fitted from measured floor points."""

    def __init__(self, rotation, translation, error_px=0):
        self.rotation = np.asarray(rotation, dtype=float)
        self.translation = np.asarray(translation, dtype=float).reshape(3)
        self.error_px = error_px

    def to_room(self, xyz_left):
        return self.rotation.T @ (xyz_left-self.translation)

    @classmethod
    def from_floor(cls, path, calibration):
        import cv2
        from .geometry import FloorHomography
        hom = FloorHomography.load(str(path))
        if hom.img_size is None or tuple(hom.img_size) != calibration.size:
            raise StereoError("Room floor alignment needs measured left-camera points at the calibrated resolution.")
        if hom.image_pts is None or hom.room_pts is None or len(hom.room_pts) < 4:
            raise StereoError("Room alignment file must retain at least four measured floor point pairs.")
        world = np.column_stack((hom.room_pts, np.zeros(len(hom.room_pts))))
        ok, rv, tv = cv2.solvePnP(world.astype(np.float64), hom.image_pts.astype(np.float64),
                                 calibration.K1, calibration.D1, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            raise StereoError("Could not solve the camera's pose relative to the floor.")
        rotation, _ = cv2.Rodrigues(rv)
        projected, _ = cv2.projectPoints(world, rv, tv, calibration.K1, calibration.D1)
        err = float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2)-hom.image_pts)**2, axis=1))))
        camera_centre = -rotation.T @ tv.reshape(3)
        depths = (world @ rotation.T+tv.reshape(3))[:, 2]
        if err > 4 or np.any(depths <= 0) or camera_centre[2] <= 0:
            raise StereoError(f"Floor pose is inconsistent (error {err:.1f}px); check shared room coordinates and clicked floor marks.")
        return cls(rotation, tv, err)
