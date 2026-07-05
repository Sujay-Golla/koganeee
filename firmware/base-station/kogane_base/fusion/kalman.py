"""Constant-velocity Kalman filter fusing (x, y) detections into a smooth estimate.

State: [x, y, vx, vy] (metres, m/s). Measurements: (x, y) from mmWave (and later the
camera centroid). Heading is derived from the velocity vector.
"""
from __future__ import annotations

import math
import numpy as np

from ..config import CONFIG


class PositionFilter:
    def __init__(self) -> None:
        self.x = np.zeros(4)              # state
        self.P = np.eye(4) * 10.0         # covariance
        self.q = CONFIG.process_noise
        self.r = CONFIG.meas_noise
        self._init = False

    def _F(self, dt: float) -> np.ndarray:
        F = np.eye(4)
        F[0, 2] = dt
        F[1, 3] = dt
        return F

    def _Q(self, dt: float) -> np.ndarray:
        # simple discrete white-noise acceleration model
        q = self.q
        dt2, dt3, dt4 = dt * dt, dt ** 3, dt ** 4
        return q * np.array([
            [dt4 / 4, 0, dt3 / 2, 0],
            [0, dt4 / 4, 0, dt3 / 2],
            [dt3 / 2, 0, dt2, 0],
            [0, dt3 / 2, 0, dt2],
        ])

    def predict(self, dt: float) -> None:
        if not self._init:
            return
        F = self._F(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self._Q(dt)

    def update(self, zx: float, zy: float) -> None:
        z = np.array([zx, zy])
        if not self._init:
            self.x[:2] = z
            self._init = True
            return
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        R = np.eye(2) * self.r
        y = z - H @ self.x
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H) @ self.P

    @property
    def position(self) -> tuple[float, float]:
        return float(self.x[0]), float(self.x[1])

    @property
    def velocity(self) -> tuple[float, float]:
        return float(self.x[2]), float(self.x[3])

    @property
    def heading_rad(self) -> float:
        vx, vy = self.velocity
        return math.atan2(vy, vx)
