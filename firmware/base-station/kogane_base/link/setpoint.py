"""Turn a fused target position into a velocity setpoint for the drone.

Simple 'follow at distance' P-controller: command a velocity toward the point that is
`follow_distance_m` from the target along the drone->target line. The ESP32 converts the
SETPOINT datagram into MSP RC override for iNAV.
"""
from __future__ import annotations

import math

from ..config import CONFIG
from ..protocol import CtrlMode, MsgType, pack_setpoint


def compute_setpoint(
    drone_xy: tuple[float, float],
    target_xy: tuple[float, float],
) -> bytes:
    dx = target_xy[0] - drone_xy[0]
    dy = target_xy[1] - drone_xy[1]
    dist = math.hypot(dx, dy)

    if dist < 1e-3:
        return pack_setpoint(0, 0, 0, 0, CtrlMode.HOLD)

    # error is how far we are from the desired standoff distance
    err = dist - CONFIG.follow_distance_m
    ux, uy = dx / dist, dy / dist                 # unit vector drone->target
    speed_ms = CONFIG.kp_xy * err                 # + toward target, - back off
    vx = int(max(-CONFIG.max_speed_cms, min(CONFIG.max_speed_cms, ux * speed_ms * 100)))
    vy = int(max(-CONFIG.max_speed_cms, min(CONFIG.max_speed_cms, uy * speed_ms * 100)))

    # yaw to face the target (drone-relative); vz held (altitude via VL53L1X on FC)
    yaw_rate_cds = 0  # TODO(kogane): close a heading loop using drone_state.yaw
    return pack_setpoint(vx, vy, 0, yaw_rate_cds, CtrlMode.VELOCITY)


SETPOINT_MSG = MsgType.SETPOINT
