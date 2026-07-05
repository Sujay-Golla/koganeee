"""Python mirror of firmware/shared/PROTOCOL.md (KGN UDP datagram)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"KGN"
VERSION = 1

# header: 3s magic, B version, B type, B flags, H seq, I src_id, H len
_HDR = struct.Struct("<3sBBBHIH")
HEADER_LEN = _HDR.size  # 14


class MsgType(IntEnum):
    MMWAVE_TARGETS = 0x01
    SETPOINT = 0x10
    MODE_CMD = 0x11
    DRONE_STATE = 0x20
    SCREEN_FRAME = 0x30
    AUDIO_TTS = 0x40
    AUDIO_MIC = 0x41
    HEARTBEAT = 0x7F


class CtrlMode(IntEnum):
    HOLD = 0
    VELOCITY = 1
    POSITION = 2


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def pack(msg_type: int, payload: bytes, seq: int = 0, src_id: int = 0, flags: int = 0) -> bytes:
    hdr = _HDR.pack(MAGIC, VERSION, int(msg_type), flags, seq & 0xFFFF, src_id, len(payload))
    frame = hdr + payload
    return frame + struct.pack("<H", crc16_ccitt(frame))


@dataclass
class Frame:
    msg_type: int
    seq: int
    src_id: int
    payload: bytes


def unpack(data: bytes) -> Frame | None:
    if len(data) < HEADER_LEN + 2:
        return None
    magic, ver, mtype, flags, seq, src_id, plen = _HDR.unpack(data[:HEADER_LEN])
    if magic != MAGIC or ver != VERSION:
        return None
    if len(data) < HEADER_LEN + plen + 2:
        return None
    body_end = HEADER_LEN + plen
    (crc,) = struct.unpack("<H", data[body_end:body_end + 2])
    if crc != crc16_ccitt(data[:body_end]):
        return None
    return Frame(mtype, seq, src_id, data[HEADER_LEN:body_end])


# ---- payload (de)serializers ----
_TARGET = struct.Struct("<hhhH")  # x_mm, y_mm, speed_cms, res_mm


def parse_mmwave(payload: bytes) -> list[tuple[int, int, int, int]]:
    if not payload:
        return []
    count = payload[0]
    out = []
    off = 1
    for _ in range(count):
        if off + _TARGET.size > len(payload):
            break
        out.append(_TARGET.unpack(payload[off:off + _TARGET.size]))
        off += _TARGET.size
    return out


_SETPOINT = struct.Struct("<hhhhB")  # vx, vy, vz, yaw_rate, ctrl_mode


def pack_setpoint(vx: int, vy: int, vz: int, yaw_rate: int, mode: CtrlMode) -> bytes:
    return _SETPOINT.pack(vx, vy, vz, yaw_rate, int(mode))
