"""Byte-level tests for the HLK-LD2450 report decoder.

Everything here is synthetic bytes — no serial port, no radar. The frames are hand-built
from the documented layout (header AA FF 03 00, 3 × 8-byte targets, footer 55 CC) rather
than captured from hardware, so what these tests pin is *the decode we intend*, including
the sign-magnitude convention taken from ESPHome's ld2450 component. If a physical module
ever disagrees, it will disagree about sign, and `test_sign_bit_polarity` is the one to
change.
"""
from __future__ import annotations

import struct

import pytest

from kogane_base.tracking import ld2450 as d


# ---- helpers ---------------------------------------------------------------
def raw_target(x_mm: int, y_mm: int, speed_cms: int, res_mm: int = 100) -> bytes:
    """Build one 8-byte slot the way the module would report it (sign bit = positive)."""
    return struct.pack("<HHHH", d.encode_signed(x_mm), d.encode_signed(y_mm),
                       d.encode_signed(speed_cms), res_mm)


EMPTY_SLOT = bytes(8)


def frame(*slots: bytes) -> bytes:
    body = b"".join(slots) + EMPTY_SLOT * (d.MAX_TARGETS - len(slots))
    return d.HEADER + body + d.FOOTER


# ---- layout constants -----------------------------------------------------
def test_frame_geometry_matches_the_datasheet_layout():
    assert d.HEADER == b"\xaa\xff\x03\x00"
    assert d.FOOTER == b"\x55\xcc"
    assert d.TARGET_LEN == 8
    assert d.MAX_TARGETS == 3
    assert d.FRAME_LEN == 30


# ---- sign-magnitude decode ------------------------------------------------
def test_sign_bit_polarity():
    """Bit 15 set means positive; clear means negative. Not two's complement."""
    assert d.decode_signed(0x81F4) == 500     # 0x8000 | 500
    assert d.decode_signed(0x01F4) == -500
    # A naive little-endian int16 read would have given these instead:
    assert struct.unpack("<h", struct.pack("<H", 0x81F4))[0] == -32268
    assert struct.unpack("<h", struct.pack("<H", 0x01F4))[0] == 500


@pytest.mark.parametrize("raw,expected", [
    (0x0000, 0),          # no sign bit, zero magnitude
    (0x8000, 0),          # sign bit, zero magnitude
    (0x7FFF, -32767),     # largest negative
    (0xFFFF, 32767),      # largest positive
])
def test_decode_signed_edges(raw, expected):
    assert d.decode_signed(raw) == expected


@pytest.mark.parametrize("value", [0, 1, -1, 500, -500, 32767, -32767])
def test_encode_decode_signed_round_trip(value):
    assert d.decode_signed(d.encode_signed(value)) == value


def test_encode_signed_rejects_out_of_range():
    with pytest.raises(ValueError):
        d.encode_signed(32768)


# ---- single-frame decode --------------------------------------------------
def test_clean_frame_decodes_one_target():
    f = frame(raw_target(1200, 2300, -45, res_mm=160))
    targets = d.decode_report(f)
    assert targets == [d.Target(1200, 2300, -45, 160)]


def test_three_targets_decode_in_slot_order():
    f = frame(raw_target(100, 200, 1), raw_target(300, 400, 2), raw_target(500, 600, 3))
    assert d.decode_report(f) == [
        d.Target(100, 200, 1, 100),
        d.Target(300, 400, 2, 100),
        d.Target(500, 600, 3, 100),
    ]


def test_empty_slots_are_dropped_not_reported_as_origin_targets():
    f = frame(EMPTY_SLOT, raw_target(-800, 1500, 0), EMPTY_SLOT)
    assert d.decode_report(f) == [d.Target(-800, 1500, 0, 100)]


def test_idle_radar_decodes_to_an_empty_report_not_a_failure():
    f = frame()                      # all three slots zero
    assert d.decode_report(f) == []  # a report, not None


@pytest.mark.parametrize("x_mm,y_mm", [
    (-1500, 2000),    # negative x only
    (1500, -2000),    # negative y only
    (-1500, -2000),   # both negative
    (0, 3000),        # on the boresight
])
def test_negative_coordinates_in_each_axis(x_mm, y_mm):
    f = frame(raw_target(x_mm, y_mm, -30))
    assert d.decode_report(f) == [d.Target(x_mm, y_mm, -30, 100)]


def test_resolution_is_unsigned():
    slot = struct.pack("<HHHH", d.encode_signed(10), d.encode_signed(20),
                       d.encode_signed(0), 0xFF00)
    assert d.decode_report(frame(slot)) == [d.Target(10, 20, 0, 0xFF00)]


def test_decode_report_rejects_bad_frames():
    good = frame(raw_target(1, 2, 3))
    assert d.decode_report(good) is not None
    assert d.decode_report(good[:-1]) is None                  # wrong length
    assert d.decode_report(b"\x00" + good[1:]) is None         # bad header
    assert d.decode_report(good[:-2] + b"\x55\xff") is None    # bad footer


def test_decode_target_rejects_a_wrong_sized_slot():
    with pytest.raises(ValueError):
        d.decode_target(b"\x00" * 7)


def test_encode_report_round_trips_and_pads():
    targets = [d.Target(-250, 1750, 60, 40)]
    buf = d.encode_report(targets)
    assert len(buf) == d.FRAME_LEN
    assert d.decode_report(buf) == targets


def test_encode_report_rejects_too_many_targets():
    with pytest.raises(ValueError):
        d.encode_report([d.Target(1, 1, 0, 0)] * 4)


# ---- streaming parser ----------------------------------------------------
def test_stream_clean_frame():
    p = d.Ld2450Parser()
    reports = p.feed(frame(raw_target(1000, 2000, 10)))
    assert reports == [[d.Target(1000, 2000, 10, 100)]]
    assert p.frames_decoded == 1
    assert p.pending_bytes == 0


def test_stream_frame_split_across_three_reads():
    f = frame(raw_target(1111, 2222, -33))
    p = d.Ld2450Parser()
    assert p.feed(f[:7]) == []        # split inside target 0
    assert p.feed(f[7:19]) == []      # split inside target 1
    reports = p.feed(f[19:])
    assert reports == [[d.Target(1111, 2222, -33, 100)]]
    assert p.pending_bytes == 0


def test_stream_split_inside_the_header():
    f = frame(raw_target(5, 6, 7))
    p = d.Ld2450Parser()
    for i in (1, 2, 3):
        p.reset()
        assert p.feed(f[:i]) == []
        assert p.pending_bytes == i    # a partial header must be retained
        assert p.feed(f[i:]) == [[d.Target(5, 6, 7, 100)]]


def test_stream_resynchronises_after_leading_garbage():
    f = frame(raw_target(900, 1800, 5))
    p = d.Ld2450Parser()
    reports = p.feed(b"\x11\x22\xaa\xfe\x33" + f)
    assert reports == [[d.Target(900, 1800, 5, 100)]]
    assert p.bytes_discarded == 5


def test_stream_truncated_frame_yields_nothing_and_waits():
    f = frame(raw_target(1, 2, 3))
    p = d.Ld2450Parser()
    assert p.feed(f[:-1]) == []
    assert p.pending_bytes == d.FRAME_LEN - 1
    assert p.frames_decoded == 0


def test_stream_bad_footer_is_rejected_then_resynced():
    bad = frame(raw_target(1, 2, 3))[:-2] + b"\x55\x00"
    good = frame(raw_target(4, 5, 6))
    p = d.Ld2450Parser()
    reports = p.feed(bad + good)
    assert reports == [[d.Target(4, 5, 6, 100)]]
    assert p.bad_footers == 1
    assert p.frames_decoded == 1


def test_stream_recovers_when_bytes_are_dropped_mid_frame():
    """A frame missing its middle must not swallow the next good frame."""
    f = frame(raw_target(1, 2, 3))
    good = frame(raw_target(7, 8, 9))
    p = d.Ld2450Parser()
    reports = p.feed(f[:20] + good)          # truncated frame, then a whole one
    assert reports == [[d.Target(7, 8, 9, 100)]]


def test_stream_handles_back_to_back_frames_in_one_read():
    a = frame(raw_target(10, 20, 1))
    b = frame(raw_target(30, 40, 2))
    p = d.Ld2450Parser()
    assert p.feed(a + b) == [[d.Target(10, 20, 1, 100)], [d.Target(30, 40, 2, 100)]]


def test_stream_byte_at_a_time_matches_whole_frame():
    f = frame(raw_target(-600, 2400, -12)) + frame(raw_target(600, 1200, 12))
    p = d.Ld2450Parser()
    out = []
    for i in range(len(f)):
        out += p.feed(f[i:i + 1])
    assert out == [[d.Target(-600, 2400, -12, 100)], [d.Target(600, 1200, 12, 100)]]


def test_buffer_stays_bounded_on_pure_garbage():
    """100 kB of noise, including header-lookalikes, must not grow the buffer."""
    p = d.Ld2450Parser()
    noise = bytes(range(256)) * 400          # contains 0xAA and 0xFF bytes throughout
    for i in range(0, len(noise), 997):      # awkward chunk size on purpose
        assert p.feed(noise[i:i + 997]) == []
        assert p.pending_bytes < d.FRAME_LEN
    assert p.frames_decoded == 0


def test_buffer_stays_bounded_on_repeated_false_headers():
    p = d.Ld2450Parser()
    for _ in range(500):
        p.feed(d.HEADER)
        assert p.pending_bytes < d.FRAME_LEN
    assert p.frames_decoded == 0


def test_garbage_then_stream_still_locks_on():
    p = d.Ld2450Parser()
    p.feed(b"\xaa" * 100 + b"\xaa\xff\x03")        # header-ish noise, never completing
    reports = p.feed(frame(raw_target(1234, 5678, 20)))
    assert reports == [[d.Target(1234, 5678, 20, 100)]]


def test_reset_drops_partial_state():
    f = frame(raw_target(1, 2, 3))
    p = d.Ld2450Parser()
    p.feed(f[:15])
    p.reset()
    assert p.pending_bytes == 0
    assert p.feed(f[15:]) == []            # the tail alone is not a frame


def test_parser_rejects_an_undersized_buffer_cap():
    with pytest.raises(ValueError):
        d.Ld2450Parser(max_buffer=d.FRAME_LEN - 1)


def test_empty_feed_is_a_no_op():
    p = d.Ld2450Parser()
    assert p.feed(b"") == []
    assert p.pending_bytes == 0
