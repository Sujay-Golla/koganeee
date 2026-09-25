"""Wire-format tests for kogane_base.protocol.

These pin the Python side to firmware/shared/PROTOCOL.md §1 byte-for-byte, which
is what catches a divergence from the C mirror in
companion-esp32s3/main/kogane_msg.h.
"""
from __future__ import annotations

import struct

import pytest

from kogane_base import protocol as p


# ---- CRC-16/CCITT-FALSE ----------------------------------------------------
# Pinned to the variant the doc names: poly 0x1021, init 0xFFFF, no reflection,
# no final xor. The "123456789" check value is what separates CCITT-FALSE from
# the other 0x1021 variants (XMODEM = 0x31C3, KERMIT = 0x2189).
def test_crc16_standard_check_value():
    assert p.crc16_ccitt(b"123456789") == 0x29B1


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"", 0xFFFF),
        (b"\x00", 0xE1F0),
        (b"A", 0xB915),
        (b"KGN", 0x1C91),
    ],
)
def test_crc16_known_vectors(data, expected):
    assert p.crc16_ccitt(data) == expected


def test_crc16_is_not_xmodem_or_kermit():
    crc = p.crc16_ccitt(b"123456789")
    assert crc != 0x31C3  # XMODEM (init 0x0000)
    assert crc != 0x2189  # KERMIT (reflected)


# ---- header byte layout (PROTOCOL.md §1) -----------------------------------
def test_header_len_is_14():
    assert p.HEADER_LEN == 14


def test_packed_header_field_offsets():
    payload = b"\xaa\xbb\xcc"
    frame = p.pack(p.MsgType.DRONE_STATE, payload, seq=0x1234, src_id=0xDEADBEEF, flags=0x01)

    assert frame[0:3] == b"KGN"                                   # 0  magic
    assert frame[3] == 1                                          # 3  version
    assert frame[4] == int(p.MsgType.DRONE_STATE)                 # 4  msg_type
    assert frame[5] == 0x01                                       # 5  flags
    assert frame[6:8] == struct.pack("<H", 0x1234)                # 6  seq  (LE)
    assert frame[8:12] == struct.pack("<I", 0xDEADBEEF)           # 8  src_id (LE)
    assert frame[12:14] == struct.pack("<H", len(payload))        # 12 len  (LE)
    assert frame[14:14 + len(payload)] == payload                 # 14 payload
    assert frame[17:19] == struct.pack("<H", p.crc16_ccitt(frame[:17]))  # 14+len crc

    assert len(frame) == p.HEADER_LEN + len(payload) + 2


def test_crc_covers_header_and_payload():
    frame = p.pack(p.MsgType.HEARTBEAT, b"\x01\x02\x03\x04\x05")
    body_end = len(frame) - 2
    (crc,) = struct.unpack("<H", frame[body_end:])
    assert crc == p.crc16_ccitt(frame[:body_end])


# ---- payload sizes are the documented ones --------------------------------
@pytest.mark.parametrize(
    "const,size",
    [
        (p.SETPOINT_LEN, 9),
        (p.DRONE_STATE_LEN, 12),
        (p.HEARTBEAT_LEN, 5),
        (p.MODE_CMD_LEN, 1),
    ],
)
def test_payload_struct_sizes(const, size):
    assert const == size


def test_setpoint_field_offsets():
    payload = p.pack_setpoint(-100, 200, -300, 400, p.CtrlMode.VELOCITY)
    assert len(payload) == 9
    assert payload[0:2] == struct.pack("<h", -100)   # vx_cms
    assert payload[2:4] == struct.pack("<h", 200)    # vy_cms
    assert payload[4:6] == struct.pack("<h", -300)   # vz_cms
    assert payload[6:8] == struct.pack("<h", 400)    # yaw_rate_cds
    assert payload[8] == int(p.CtrlMode.VELOCITY)    # ctrl_mode


def test_drone_state_field_offsets():
    payload = p.pack_drone_state(-1, 2, 3, -4, 11400, 0x05, 97)
    assert len(payload) == 12
    assert payload[0:2] == struct.pack("<h", -1)     # x_cm
    assert payload[2:4] == struct.pack("<h", 2)      # y_cm
    assert payload[4:6] == struct.pack("<h", 3)      # z_cm
    assert payload[6:8] == struct.pack("<h", -4)     # yaw_cd
    assert payload[8:10] == struct.pack("<H", 11400)  # batt_mv (unsigned)
    assert payload[10] == 0x05                       # flags
    assert payload[11] == 97                         # link_q


def test_heartbeat_field_offsets():
    payload = p.pack_heartbeat(0x01020304, p.Role.DRONE)
    assert len(payload) == 5
    assert payload[0:4] == struct.pack("<I", 0x01020304)  # uptime_ms
    assert payload[4] == int(p.Role.DRONE)                # role


# ---- enum values match the doc -------------------------------------------
def test_mode_enum_values():
    assert [p.Mode.IDLE, p.Mode.ARM, p.Mode.TAKEOFF, p.Mode.FOLLOW,
            p.Mode.LAND, p.Mode.DOCK, p.Mode.FAILSAFE] == [0, 1, 2, 3, 4, 5, 6]


def test_role_enum_values():
    assert [p.Role.BASE, p.Role.DRONE, p.Role.NODE] == [0, 1, 2]


# ---- pack/unpack round trips ---------------------------------------------
def test_roundtrip_setpoint():
    payload = p.pack_setpoint(-32768, 32767, 0, -1, p.CtrlMode.POSITION)
    f = p.unpack(p.pack(p.MsgType.SETPOINT, payload, seq=7, src_id=0))
    assert f is not None
    assert f.msg_type == p.MsgType.SETPOINT
    assert f.seq == 7
    sp = p.unpack_setpoint(f.payload)
    assert sp == p.Setpoint(-32768, 32767, 0, -1, int(p.CtrlMode.POSITION))


def test_roundtrip_drone_state():
    payload = p.pack_drone_state(-500, 500, 150, 18000, 12600, 0x03, 88)
    f = p.unpack(p.pack(p.MsgType.DRONE_STATE, payload, seq=0xFFFF, src_id=0))
    assert f is not None
    assert f.msg_type == p.MsgType.DRONE_STATE
    assert p.unpack_drone_state(f.payload) == p.DroneState(
        -500, 500, 150, 18000, 12600, 0x03, 88
    )


def test_roundtrip_mode_cmd():
    f = p.unpack(p.pack(p.MsgType.MODE_CMD, p.pack_mode_cmd(p.Mode.TAKEOFF)))
    assert f is not None
    assert f.msg_type == p.MsgType.MODE_CMD
    assert len(f.payload) == 1
    assert p.unpack_mode_cmd(f.payload) == int(p.Mode.TAKEOFF)


def test_roundtrip_heartbeat():
    f = p.unpack(p.pack(p.MsgType.HEARTBEAT, p.pack_heartbeat(4294967295, p.Role.NODE), src_id=3))
    assert f is not None
    assert f.msg_type == p.MsgType.HEARTBEAT
    assert f.src_id == 3
    assert p.unpack_heartbeat(f.payload) == p.Heartbeat(4294967295, int(p.Role.NODE))


def test_payload_unpackers_reject_wrong_length():
    assert p.unpack_setpoint(b"\x00" * 8) is None
    assert p.unpack_drone_state(b"\x00" * 11) is None
    assert p.unpack_heartbeat(b"\x00" * 6) is None
    assert p.unpack_mode_cmd(b"") is None


# ---- unpack() rejection cases -------------------------------------------
def _good_frame() -> bytes:
    return p.pack(p.MsgType.SETPOINT, p.pack_setpoint(1, 2, 3, 4, p.CtrlMode.VELOCITY))


def test_unpack_good_frame_is_baseline():
    assert p.unpack(_good_frame()) is not None


def test_unpack_rejects_bad_magic():
    frame = bytearray(_good_frame())
    frame[0] = ord("X")
    assert p.unpack(bytes(frame)) is None


def test_unpack_rejects_wrong_version():
    frame = bytearray(_good_frame())
    frame[3] = p.VERSION + 1
    assert p.unpack(bytes(frame)) is None


@pytest.mark.parametrize("keep", [0, 1, 13, 15, 24])
def test_unpack_rejects_truncated(keep):
    frame = _good_frame()
    assert len(frame) == 25
    assert p.unpack(frame[:keep]) is None


def test_unpack_rejects_len_longer_than_buffer():
    """h.len claims more payload than was received."""
    frame = bytearray(_good_frame())
    frame[12:14] = struct.pack("<H", 900)
    assert p.unpack(bytes(frame)) is None


@pytest.mark.parametrize("bit_index", range(0, 25 * 8, 7))
def test_unpack_rejects_single_bit_flip(bit_index):
    frame = bytearray(_good_frame())
    frame[bit_index // 8] ^= 1 << (bit_index % 8)
    # A flip anywhere in the frame must be rejected: either by magic/version/len
    # checks or by the CRC. None of them may be accepted as a valid setpoint.
    assert p.unpack(bytes(frame)) is None


def test_unpack_rejects_flipped_crc_byte():
    frame = bytearray(_good_frame())
    frame[-1] ^= 0x01
    assert p.unpack(bytes(frame)) is None
    frame = bytearray(_good_frame())
    frame[-2] ^= 0x80
    assert p.unpack(bytes(frame)) is None


def test_unpack_rejects_flipped_payload_byte():
    frame = bytearray(_good_frame())
    frame[14] ^= 0x01
    assert p.unpack(bytes(frame)) is None


# ---- mmwave_targets (PROTOCOL.md §1) --------------------------------------
# `pack_mmwave` exists for loopback testing and the mmWave simulator; the real node side
# packs this in C. It must agree with `parse_mmwave` byte for byte.
def test_mmwave_target_len_is_8():
    assert p.MMWAVE_TARGET_LEN == 8


def test_mmwave_field_offsets():
    payload = p.pack_mmwave([(-1234, 2345, -67, 40000)])
    assert len(payload) == 1 + 8
    assert payload[0] == 1                            # u8 count
    assert payload[1:3] == struct.pack("<h", -1234)   # i16 x_mm
    assert payload[3:5] == struct.pack("<h", 2345)    # i16 y_mm
    assert payload[5:7] == struct.pack("<h", -67)     # i16 speed_cms
    assert payload[7:9] == struct.pack("<H", 40000)   # u16 res_mm (unsigned)


def test_pack_mmwave_empty_is_just_a_zero_count():
    assert p.pack_mmwave([]) == b"\x00"
    assert p.parse_mmwave(p.pack_mmwave([])) == []


@pytest.mark.parametrize("targets", [
    [],
    [(0, 0, 0, 0)],
    [(1000, 2000, 30, 100)],
    [(-32768, 32767, -1, 0), (1, -1, 0, 65535), (0, 1, -32768, 1)],
    [(i * 10, -i * 10, i, i) for i in range(255)],     # max count for a u8
])
def test_roundtrip_mmwave(targets):
    assert p.parse_mmwave(p.pack_mmwave(targets)) == [tuple(t) for t in targets]


def test_roundtrip_mmwave_through_a_full_datagram():
    targets = [(1500, -2500, 45, 120), (-300, 900, -12, 80)]
    f = p.unpack(p.pack(p.MsgType.MMWAVE_TARGETS, p.pack_mmwave(targets), seq=9, src_id=1))
    assert f is not None
    assert f.msg_type == p.MsgType.MMWAVE_TARGETS
    assert f.src_id == 1
    assert p.parse_mmwave(f.payload) == targets


def test_pack_mmwave_rejects_more_than_a_u8_count():
    with pytest.raises(ValueError):
        p.pack_mmwave([(0, 0, 0, 0)] * 256)


def test_pack_mmwave_rejects_out_of_range_fields():
    with pytest.raises(struct.error):
        p.pack_mmwave([(40000, 0, 0, 0)])      # does not fit in i16


def test_parse_mmwave_stops_at_a_truncated_target():
    """Unchanged behaviour, pinned now that a packer exists to compare against."""
    full = p.pack_mmwave([(1, 2, 3, 4), (5, 6, 7, 8)])
    assert p.parse_mmwave(full[:-3]) == [(1, 2, 3, 4)]
