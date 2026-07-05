"""Base-station configuration. Override via env vars where useful."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # networking
    udp_port: int = int(os.getenv("KGN_UDP_PORT", "5005"))
    drone_ip: str = os.getenv("KGN_DRONE_IP", "192.168.4.2")

    # room geometry (metres). Origin at one corner; used to place nodes + clamp targets.
    room_w_m: float = float(os.getenv("KGN_ROOM_W", "4.0"))
    room_l_m: float = float(os.getenv("KGN_ROOM_L", "5.0"))

    # LD2450 node placements: node_id -> (x_m, y_m, yaw_deg) in the room frame.
    # TODO(kogane): set to the actual corner mounting once room dims are confirmed.
    node_poses: dict[int, tuple[float, float, float]] = field(default_factory=lambda: {
        0: (0.0, 0.0, 45.0),
        1: (4.0, 5.0, 225.0),
    })

    # follow behaviour
    follow_distance_m: float = 1.2
    max_speed_cms: int = 60          # clamp on commanded velocity
    kp_xy: float = 0.8               # position-error -> velocity gain

    # fusion
    process_noise: float = 0.5
    meas_noise: float = 0.3

    loop_hz: float = 30.0


CONFIG = Config()
