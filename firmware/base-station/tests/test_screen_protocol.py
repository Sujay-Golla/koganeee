"""Wire-format tests for SCREEN_FRAME (0x30) in kogane_base.protocol.

Pinned against the offset tables in firmware/shared/PROTOCOL.md §1 and the acceptance rules
in companion-esp32s3/main/display_spi.c. Pure byte assertions: no socket, no drone, no PIL.
"""
from __future__ import annotations

import struct

import numpy as np
import pytest

from kogane_base import protocol as p


# ---- panel and budget constants -------------------------------------------
def test_panel_is_320x240_landscape():
    assert (p.SCREEN_W, p.SCREEN_H) == (320, 240)


def test_band_buffer_is_320x32():
    assert p.SCREEN_BAND_PIXELS == 320 * 32 == 10240


def test_tile_budget_is_1440_bytes_720_pixels():
    # 1500 MTU - 28 IP/UDP - 14 KGN header - 2 crc - 8 sub-header - 8 tile header
    assert p.SCREEN_TILE_MAX_BODY == 1500 - 28 - 14 - 2 - 8 - 8 == 1440
    assert p.SCREEN_TILE_MAX_PIXELS == 720


def test_a_full_width_strip_of_2_rows_fits_and_3_does_not():
    assert 320 * 2 * 2 == 1280 <= p.SCREEN_TILE_MAX_BODY
    assert 320 * 3 * 2 == 1920 > p.SCREEN_TILE_MAX_BODY


def test_text_grid_is_10_rows_of_24px_and_53_chars():
    assert p.SCREEN_TEXT_ROWS == 10
    assert p.SCREEN_TEXT_ROW_PX == 24
    assert p.SCREEN_TEXT_ROWS * p.SCREEN_TEXT_ROW_PX == p.SCREEN_H
    assert p.SCREEN_TEXT_MAX == 53
    assert p.SCREEN_TEXT_SCALE_MAX == p.SCREEN_TEXT_ROW_PX // 8 == 3


def test_screen_enum_and_flag_values():
    assert (p.ScreenFmt.RGB565, p.ScreenFmt.TEXT) == (1, 2)
    assert (p.SF_F_FIRST, p.SF_F_LAST, p.SF_F_STATUS) == (0x01, 0x02, 0x04)


# ---- sub-header byte layout ------------------------------------------------
def test_screen_sub_header_len_is_8():
    assert p.SCREEN_HDR_LEN == 8
    assert p.SCREEN_TILE_LEN == 8
    assert p.SCREEN_TEXT_LEN == 6


def test_screen_sub_header_field_offsets():
    hdr = p.pack_screen_header(p.ScreenFmt.RGB565, frame_id=0x7A, chunk_idx=0x0B,
                               chunk_cnt=0x78, flags=p.SF_F_FIRST | p.SF_F_LAST)
    assert len(hdr) == 8
    assert hdr[0] == 1           # 0 fmt
    assert hdr[1] == 0x7A        # 1 frame_id
    assert hdr[2] == 0x0B        # 2 chunk_idx
    assert hdr[3] == 0x78        # 3 chunk_cnt
    assert hdr[4] == 0x03        # 4 flags
    assert hdr[5:8] == b"\x00\x00\x00"   # 5 reserved, must be 0


def test_screen_sub_header_reserved_is_always_zero():
    for fmt in (1, 2):
        for flags in (0, 1, 2, 4, 7, 0xFF):
            assert p.pack_screen_header(fmt, 1, 2, 3, flags)[5:8] == b"\x00\x00\x00"


def test_screen_header_fields_wrap_at_a_byte():
    hdr = p.pack_screen_header(1, frame_id=256, chunk_idx=257, chunk_cnt=511, flags=256)
    assert hdr[1:5] == bytes((0, 1, 255, 0))


def test_unpack_screen_header_roundtrip():
    hdr = p.pack_screen_header(p.ScreenFmt.TEXT, 9, 3, 4, p.SF_F_LAST)
    assert p.unpack_screen_header(hdr) == p.ScreenHeader(2, 9, 3, 4, p.SF_F_LAST)


@pytest.mark.parametrize("keep", [0, 1, 7])
def test_unpack_screen_header_rejects_short(keep):
    assert p.unpack_screen_header(p.pack_screen_header(1)[:keep]) is None


# ---- fmt = 1 tile ----------------------------------------------------------
def test_tile_header_field_offsets():
    body = p.pack_screen_tile_header(0x0140 - 320, 239, 320, 1)
    assert len(body) == 8
    assert body[0:2] == struct.pack("<H", 0)      # 8  x
    assert body[2:4] == struct.pack("<H", 239)    # 10 y
    assert body[4:6] == struct.pack("<H", 320)    # 12 w
    assert body[6:8] == struct.pack("<H", 1)      # 14 h


def test_tile_payload_layout_matches_the_doc():
    px = p.rgb565_bytes(np.zeros((2, 4, 3), dtype=np.uint8))
    payload = p.screen_tile_payload(16, 32, 4, 2, px, frame_id=5, chunk_idx=1,
                                    chunk_cnt=120, flags=p.SF_F_FIRST)
    assert payload[0] == int(p.ScreenFmt.RGB565)
    assert payload[8:10] == struct.pack("<H", 16)    # offset 8  x
    assert payload[10:12] == struct.pack("<H", 32)   # offset 10 y
    assert payload[12:14] == struct.pack("<H", 4)    # offset 12 w
    assert payload[14:16] == struct.pack("<H", 2)    # offset 14 h
    assert payload[16:] == px                        # offset 16 pixels
    assert len(payload) == 8 + 8 + 4 * 2 * 2


def test_tile_payload_roundtrip_through_a_full_datagram():
    rgb = np.random.default_rng(7).integers(0, 256, size=(2, 320, 3), dtype=np.uint8)
    px = p.rgb565_bytes(rgb)
    payload = p.screen_tile_payload(0, 100, 320, 2, px, frame_id=3, chunk_idx=50,
                                    chunk_cnt=120, flags=p.SF_F_LAST)
    frame = p.unpack(p.pack(p.MsgType.SCREEN_FRAME, payload, seq=11))
    assert frame is not None
    assert frame.msg_type == p.MsgType.SCREEN_FRAME
    hdr = p.unpack_screen_header(frame.payload)
    assert hdr == p.ScreenHeader(1, 3, 50, 120, p.SF_F_LAST)
    tile = p.unpack_screen_tile(frame.payload)
    assert tile is not None
    assert (tile.x, tile.y, tile.w, tile.h) == (0, 100, 320, 2)
    assert tile.pixels == px


def test_a_full_width_2_row_strip_is_a_1312_byte_datagram():
    """14 header + 8 sub + 8 tile + 1280 pixels + 2 crc. Under the 1500 MTU with IP/UDP."""
    px = b"\x00" * (320 * 2 * 2)
    frame = p.pack(p.MsgType.SCREEN_FRAME, p.screen_tile_payload(0, 0, 320, 2, px))
    assert len(frame) == 1312
    assert len(frame) + 28 < 1500


# ---- fmt = 1 geometry validation (display_spi.c handle_rgb565) --------------
@pytest.mark.parametrize("x,y,w,h", [
    (1, 0, 320, 2),      # x + w = 321 > 320
    (0, 239, 320, 2),    # y + h = 241 > 240
    (320, 0, 1, 1),      # x at the edge
    (0, 240, 1, 1),      # y at the edge
])
def test_tile_off_the_panel_is_rejected(x, y, w, h):
    with pytest.raises(ValueError, match="runs off"):
        p.screen_tile_payload(x, y, w, h, b"\x00" * (w * h * 2))


@pytest.mark.parametrize("w,h", [(0, 2), (320, 0), (0, 0)])
def test_empty_tile_is_rejected(w, h):
    with pytest.raises(ValueError, match="non-empty"):
        p.screen_tile_payload(0, 0, w, h, b"\x00" * 16)


def test_tile_larger_than_the_band_buffer_is_rejected():
    """320x33 = 10560 px > the drone's 320x32 band buffer."""
    with pytest.raises(ValueError, match="band buffer"):
        p.check_tile_geometry(0, 0, 320, 33)


def test_tile_within_the_band_buffer_but_over_the_datagram_budget_is_rejected():
    """320x32 fits the band buffer and still cannot cross the wire in one datagram."""
    p.check_tile_geometry(0, 0, 320, 32)          # geometry alone is fine
    with pytest.raises(ValueError, match="Split it into strips"):
        p.screen_tile_payload(0, 0, 320, 32, b"\x00" * (320 * 32 * 2))


def test_short_tile_body_is_rejected():
    with pytest.raises(ValueError, match="needs 1280 pixel bytes"):
        p.screen_tile_payload(0, 0, 320, 2, b"\x00" * 1279)


def test_negative_tile_origin_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        p.screen_tile_payload(-1, 0, 4, 2, b"\x00" * 16)


def test_extra_pixel_bytes_are_trimmed_not_rejected():
    payload = p.screen_tile_payload(0, 0, 2, 1, b"\xff" * 64)
    assert len(payload) == 8 + 8 + 4


def test_unpack_screen_tile_rejects_a_short_body():
    good = p.screen_tile_payload(0, 0, 320, 2, b"\x11" * 1280)
    assert p.unpack_screen_tile(good) is not None
    assert p.unpack_screen_tile(good[:-1]) is None            # one pixel byte missing
    assert p.unpack_screen_tile(good[:p.SCREEN_HDR_LEN + 4]) is None   # partial header


def test_unpack_screen_tile_rejects_a_text_chunk():
    assert p.unpack_screen_tile(p.screen_text_payload("hi")) is None


# ---- fmt = 2 text ----------------------------------------------------------
def test_text_header_field_offsets():
    payload = p.screen_text_payload("OK", row=9, scale=3, fg=0xF800, bg=0x001F,
                                    frame_id=2, chunk_idx=0, chunk_cnt=1,
                                    flags=p.SF_F_LAST)
    assert payload[0] == int(p.ScreenFmt.TEXT)
    assert payload[8] == 9                            # offset 8  row
    assert payload[9] == 3                            # offset 9  scale
    assert payload[10:12] == struct.pack("<H", 0xF800)  # offset 10 fg
    assert payload[12:14] == struct.pack("<H", 0x001F)  # offset 12 bg
    assert payload[14:] == b"OK"                      # offset 14 text
    assert len(payload) == 8 + 6 + 2


def test_text_is_not_nul_terminated():
    payload = p.screen_text_payload("abc")
    assert payload[14:] == b"abc"
    assert not payload.endswith(b"\x00")


def test_text_at_exactly_53_chars_is_accepted():
    payload = p.screen_text_payload("x" * p.SCREEN_TEXT_MAX)
    assert len(payload) == 8 + 6 + 53


def test_text_over_53_chars_is_rejected_by_the_encoder():
    with pytest.raises(ValueError, match="truncates at 53"):
        p.screen_text_payload("x" * (p.SCREEN_TEXT_MAX + 1))


def test_empty_text_is_legal_and_clears_the_row_to_bg():
    payload = p.screen_text_payload("", row=4, bg=0x001F)
    assert len(payload) == 8 + 6
    parsed = p.unpack_screen_text(payload)
    assert parsed is not None and parsed.text == "" and parsed.bg == 0x001F


@pytest.mark.parametrize("row", [-1, 10, 255])
def test_text_row_outside_0_to_9_is_rejected(row):
    with pytest.raises(ValueError, match="row must be"):
        p.screen_text_payload("hi", row=row)


def test_non_ascii_text_is_rejected_unless_sanitised():
    with pytest.raises((ValueError, UnicodeEncodeError)):
        p.screen_text_payload("caf\u00e9")
    assert p.screen_text_sanitise("caf\u00e9") == "caf?"
    assert p.screen_text_payload(p.screen_text_sanitise("caf\u00e9"))[14:] == b"caf?"


def test_sanitise_replaces_control_and_high_characters_only():
    assert p.screen_text_sanitise("a\tb\nc") == "a?b?c"
    assert p.screen_text_sanitise(" ~") == " ~"          # the boundary chars survive
    assert p.screen_text_sanitise("\x1f\x7f") == "??"     # just outside on both sides


def test_unpack_screen_text_roundtrip():
    payload = p.screen_text_payload("LINK 97", row=5, scale=2, fg=0x07E0, bg=0x0000)
    parsed = p.unpack_screen_text(payload)
    assert parsed == p.ScreenTextLine(5, 2, 0x07E0, 0x0000, "LINK 97")


def test_unpack_screen_text_rejects_short_and_wrong_fmt():
    assert p.unpack_screen_text(p.screen_text_payload("hi")[:13]) is None
    assert p.unpack_screen_text(
        p.screen_tile_payload(0, 0, 1, 1, b"\x00\x00")) is None


# ---- STATUS ----------------------------------------------------------------
def test_status_payload_is_a_bare_sub_header_with_the_status_flag():
    payload = p.screen_status_payload(frame_id=17)
    assert len(payload) == p.SCREEN_HDR_LEN
    hdr = p.unpack_screen_header(payload)
    assert hdr is not None
    assert hdr.flags & p.SF_F_STATUS
    assert hdr.frame_id == 17
    assert payload[5:8] == b"\x00\x00\x00"


def test_status_datagram_is_24_bytes():
    assert len(p.pack(p.MsgType.SCREEN_FRAME, p.screen_status_payload())) == 14 + 8 + 2


# ---- RGB565 ----------------------------------------------------------------
# Hand-computed: red is bits 15..11, green 10..5, blue 4..0.
#   red   (255,0,0)  -> 11111 000000 00000 = 0xF800
#   green (0,255,0)  -> 00000 111111 00000 = 0x07E0
#   blue  (0,0,255)  -> 00000 000000 11111 = 0x001F
@pytest.mark.parametrize("rgb,expected", [
    ((0, 0, 0), 0x0000),
    ((255, 255, 255), 0xFFFF),
    ((255, 0, 0), 0xF800),
    ((0, 255, 0), 0x07E0),
    ((0, 0, 255), 0x001F),
    ((255, 255, 0), 0xFFE0),      # yellow = red | green
    ((0, 255, 255), 0x07FF),      # cyan   = green | blue
    ((255, 0, 255), 0xF81F),      # magenta= red | blue
    ((128, 128, 128), 0x8410),    # 10000 100000 10000
    ((255, 165, 0), 0xFD20),      # amber: 11111 101001 00000
])
def test_rgb565_hand_computed(rgb, expected):
    assert p.rgb565(*rgb) == expected


def test_rgb565_named_constants_agree_with_the_packer():
    assert p.RGB565_BLACK == p.rgb565(0, 0, 0)
    assert p.RGB565_WHITE == p.rgb565(255, 255, 255)
    assert p.RGB565_RED == p.rgb565(255, 0, 0)
    assert p.RGB565_GREEN == p.rgb565(0, 255, 0)
    assert p.RGB565_BLUE == p.rgb565(0, 0, 255)
    assert p.RGB565_CYAN == p.rgb565(0, 255, 255)
    assert p.RGB565_MAGENTA == p.rgb565(255, 0, 255)
    assert p.RGB565_YELLOW == p.rgb565(255, 255, 0)
    assert p.RGB565_AMBER == p.rgb565(255, 165, 0)
    assert p.RGB565_GREY == p.rgb565(128, 128, 128)


def test_rgb565_drops_the_low_bits_not_the_high_ones():
    """A 3-bit change in red must not move the packed value; a 8-bit one must."""
    assert p.rgb565(0b11111_000, 0, 0) == p.rgb565(0b11111_111, 0, 0)
    assert p.rgb565(0b11110_000, 0, 0) != p.rgb565(0b11111_000, 0, 0)
    assert p.rgb565(0, 0b111111_00, 0) == p.rgb565(0, 0b111111_11, 0)


def test_rgb565_bytes_is_little_endian():
    """Red is 0xF800, so the low byte 0x00 comes first on the wire."""
    assert p.rgb565_bytes(np.array([[255, 0, 0]], dtype=np.uint8)) == b"\x00\xf8"
    assert p.rgb565_bytes(np.array([[0, 255, 0]], dtype=np.uint8)) == b"\xe0\x07"
    assert p.rgb565_bytes(np.array([[0, 0, 255]], dtype=np.uint8)) == b"\x1f\x00"
    assert p.rgb565_bytes(np.array([[255, 255, 255]], dtype=np.uint8)) == b"\xff\xff"
    assert p.rgb565_bytes(np.array([[0, 0, 0]], dtype=np.uint8)) == b"\x00\x00"


def test_rgb565_bytes_is_row_major_with_no_padding():
    img = np.array([[[255, 0, 0], [0, 255, 0]],
                    [[0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
    assert p.rgb565_bytes(img) == (b"\x00\xf8" b"\xe0\x07"
                                   b"\x1f\x00" b"\xff\xff")


def test_rgb565_bytes_length_is_two_per_pixel():
    for shape in [(1, 1, 3), (2, 320, 3), (240, 320, 3), (7, 3)]:
        n = int(np.prod(shape[:-1]))
        assert len(p.rgb565_bytes(np.zeros(shape, dtype=np.uint8))) == 2 * n


def test_rgb565_bytes_rejects_a_non_rgb_array():
    with pytest.raises(ValueError, match="last axis 3"):
        p.rgb565_bytes(np.zeros((4, 4), dtype=np.uint8))


def test_rgb565_bytes_clips_and_casts_float_input():
    out = p.rgb565_bytes(np.array([[300.0, -5.0, 128.4]]))
    assert out == struct.pack("<H", p.rgb565(255, 0, 128))


def test_rgb565_roundtrip_is_stable_after_one_pass():
    rgb = np.random.default_rng(3).integers(0, 256, size=(4, 5, 3), dtype=np.uint8)
    once = p.rgb565_bytes(rgb)
    back = p.rgb565_to_rgb(once, 5, 4)
    assert back.shape == (4, 5, 3)
    assert p.rgb565_bytes(back) == once


def test_rgb565_to_rgb_rejects_a_short_buffer():
    with pytest.raises(ValueError, match="need 1280 bytes"):
        p.rgb565_to_rgb(b"\x00" * 1279, 320, 2)
