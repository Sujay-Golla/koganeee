"""Estimate a person's position from a monocular bounding box.

This is deliberately simple and testable on a webcam. Two estimates are provided:

1. `bearing_deg`  — horizontal angle off the camera axis (very reliable).
2. `distance_m`   — from apparent person height using a pinhole model and an assumed
                    real height. Rough (±20-40%) but good enough to test the fusion/
                    follow loop and to sanity-check that "closer = bigger" works.

From (distance, bearing) we produce a camera-frame (x=lateral, y=forward) point.

For the *fixed room camera*, a ground-plane homography (4 clicked floor points) is far
more accurate than height-based distance — see `TODO(kogane)` in `project_to_room`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


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
    """
    # TODO(kogane): for the fixed room camera, replace height-based distance with a
    # floor-plane homography calibrated from 4 known floor points (cv2.findHomography).
    ox, oy, yaw_deg = cam_pose
    a = math.radians(yaw_deg)
    rx = ox + est.x_m * math.cos(a) - est.y_m * math.sin(a)
    ry = oy + est.x_m * math.sin(a) + est.y_m * math.cos(a)
    return rx, ry
