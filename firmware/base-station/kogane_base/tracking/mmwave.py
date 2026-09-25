"""Turn LD2450 node datagrams into room-frame detections.

Each node reports targets in its own sensor frame (mm, sensor at origin, y forward).
We rotate/translate into the shared room frame using the node pose from config.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import CONFIG
from ..protocol import parse_mmwave


@dataclass
class Detection:
    x_m: float
    y_m: float
    speed_ms: float
    node_id: int


def node_frame_to_room(node_id: int, x_mm: int, y_mm: int) -> tuple[float, float]:
    pose = CONFIG.node_poses.get(node_id)
    if pose is None:
        return x_mm / 1000.0, y_mm / 1000.0
    ox, oy, yaw_deg = pose
    a = math.radians(yaw_deg)
    x = x_mm / 1000.0
    y = y_mm / 1000.0
    rx = ox + x * math.cos(a) - y * math.sin(a)
    ry = oy + x * math.sin(a) + y * math.cos(a)
    return rx, ry


def room_to_node_frame(node_id: int, x_m: float, y_m: float) -> tuple[int, int]:
    """Exact inverse of `node_frame_to_room`: room metres -> that node's sensor frame, mm.

    Only used to *generate* detections (the mmWave simulator synthesises a room-frame path
    and has to express it the way a node at that pose would have reported it). Rounds to
    whole millimetres, which is the radar's own resolution.
    """
    pose = CONFIG.node_poses.get(node_id)
    if pose is None:
        return round(x_m * 1000.0), round(y_m * 1000.0)
    ox, oy, yaw_deg = pose
    a = math.radians(yaw_deg)
    dx = x_m - ox
    dy = y_m - oy
    x = dx * math.cos(a) + dy * math.sin(a)
    y = -dx * math.sin(a) + dy * math.cos(a)
    return round(x * 1000.0), round(y * 1000.0)


def detections_from_payload(node_id: int, payload: bytes) -> list[Detection]:
    dets: list[Detection] = []
    for x_mm, y_mm, speed_cms, _res in parse_mmwave(payload):
        if x_mm == 0 and y_mm == 0:
            continue
        rx, ry = node_frame_to_room(node_id, x_mm, y_mm)
        dets.append(Detection(rx, ry, speed_cms / 100.0, node_id))
    # TODO(kogane): pick the person target when multiple detections (nearest to last
    #               estimate, or camera-confirmed identity). For now return all.
    return dets
