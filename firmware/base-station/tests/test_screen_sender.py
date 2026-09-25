"""Tests for kogane_base.screen: chunking, flags, truncation, and a real loopback socket.

Everything up to `test_loopback_*` is pure. The loopback tests bind a UDP socket on
127.0.0.1 and send to it, so the whole encode path — payload build, KGN framing, CRC,
sendto, recvfrom, unpack — runs for real with no drone present. No hardware is involved
anywhere in this file.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import struct
import threading

import numpy as np
import pytest

from kogane_base import protocol as p
from kogane_base.net.sink import EndpointSink, ListSink, SocketSink
from kogane_base.net.udp import UdpEndpoint
from kogane_base.screen import sender as s
from kogane_base.screen.frames import ReadoutState, readout_lines
from kogane_base.screen.renderer import ScreenRenderer
from kogane_base.screen.sender import ScreenSender


def _blank(w: int = 320, h: int = 240) -> bytes:
    return b"\x00" * (w * h * 2)


# ---- strip geometry --------------------------------------------------------
def test_max_strip_rows_for_a_full_width_panel_is_2():
    assert s.max_strip_rows(320) == 2


@pytest.mark.parametrize("w,expected", [
    (320, 2),      # 1280 bytes
    (160, 4),      # 1280 bytes
    (40, 18),      # 1440 bytes exactly
    (1, 720),      # capped by the 720-pixel datagram budget, not the band buffer
])
def test_max_strip_rows(w, expected):
    assert s.max_strip_rows(w) == expected


def test_max_strip_rows_never_exceeds_either_limit():
    for w in range(1, 321):
        rows = s.max_strip_rows(w)
        assert w * rows <= p.SCREEN_TILE_MAX_PIXELS
        assert w * rows <= p.SCREEN_BAND_PIXELS


# ---- image tiling ---------------------------------------------------------
def test_a_full_frame_is_120_strips_of_two_rows():
    payloads = s.image_payloads(_blank(), strip_rows=2)
    assert len(payloads) == 120
    assert all(len(pl) == 8 + 8 + 1280 for pl in payloads)


def test_full_frame_chunk_indices_and_count_are_correct():
    payloads = s.image_payloads(_blank(), frame_id=42, strip_rows=2)
    for i, pl in enumerate(payloads):
        hdr = p.unpack_screen_header(pl)
        assert hdr == p.ScreenHeader(int(p.ScreenFmt.RGB565), 42, i, 120,
                                     hdr.flags)


def test_full_frame_flags_are_first_on_the_first_and_last_on_the_last():
    payloads = s.image_payloads(_blank(), strip_rows=2)
    flags = [p.unpack_screen_header(pl).flags for pl in payloads]
    assert flags[0] == p.SF_F_FIRST
    assert flags[-1] == p.SF_F_LAST
    assert all(f == 0 for f in flags[1:-1])
    assert not any(f & p.SF_F_STATUS for f in flags)


def test_clear_false_drops_the_first_flag_only():
    flags = [p.unpack_screen_header(pl).flags
             for pl in s.image_payloads(_blank(), strip_rows=2, clear=False)]
    assert flags[0] == 0
    assert flags[-1] == p.SF_F_LAST


def test_strips_tile_the_panel_exactly_once_top_to_bottom():
    tiles = [p.unpack_screen_tile(pl) for pl in s.image_payloads(_blank(), strip_rows=2)]
    assert all(t is not None for t in tiles)
    assert [t.y for t in tiles] == list(range(0, 240, 2))
    assert all((t.x, t.w, t.h) == (0, 320, 2) for t in tiles)
    assert sum(t.w * t.h for t in tiles) == 320 * 240


def test_every_strip_passes_the_drones_geometry_rules():
    for pl in s.image_payloads(_blank(), strip_rows=2):
        t = p.unpack_screen_tile(pl)
        assert t.x + t.w <= p.SCREEN_W
        assert t.y + t.h <= p.SCREEN_H
        assert t.w * t.h <= p.SCREEN_BAND_PIXELS
        assert len(t.pixels) == t.w * t.h * 2
        assert len(p.pack(p.MsgType.SCREEN_FRAME, pl)) + 28 <= 1500


def test_pixels_land_in_the_right_strip():
    """Row 100 is pure red, everything else black: only the strip at y=100 carries it."""
    rgb = np.zeros((240, 320, 3), dtype=np.uint8)
    rgb[100, :, 0] = 255
    payloads = s.image_payloads(p.rgb565_bytes(rgb), strip_rows=2)
    red = p.rgb565_bytes(np.array([[255, 0, 0]], dtype=np.uint8))
    for pl in payloads:
        t = p.unpack_screen_tile(pl)
        if t.y == 100:
            assert t.pixels[:2] == red                 # first pixel of the top row
            assert t.pixels[320 * 2:320 * 2 + 2] == b"\x00\x00"   # second row is black
        else:
            assert set(t.pixels) == {0}


def test_a_final_short_strip_is_emitted_for_a_height_that_does_not_divide():
    payloads = s.image_payloads(_blank(320, 5), h=5, strip_rows=2)
    heights = [p.unpack_screen_tile(pl).h for pl in payloads]
    assert heights == [2, 2, 1]
    assert p.unpack_screen_header(payloads[-1]).flags & p.SF_F_LAST


def test_a_single_strip_frame_carries_both_first_and_last():
    payloads = s.image_payloads(_blank(320, 2), h=2, strip_rows=2)
    assert len(payloads) == 1
    assert p.unpack_screen_header(payloads[0]).flags == p.SF_F_FIRST | p.SF_F_LAST


def test_strip_rows_over_the_budget_is_clamped_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="kogane.screen"):
        payloads = s.image_payloads(_blank(), strip_rows=32)
    assert len(payloads) == 120
    assert "over the" in caplog.text


def test_one_row_strips_are_240_chunks_and_still_fit_the_u8_counters():
    """240 is the most strips a valid 320x240 frame can need, so the u8 never overflows."""
    payloads = s.image_payloads(_blank(), strip_rows=1)
    assert len(payloads) == 240
    hdrs = [p.unpack_screen_header(pl) for pl in payloads]
    assert all(h.chunk_cnt == 240 for h in hdrs)
    assert [h.chunk_idx for h in hdrs] == list(range(240))
    assert all(p.unpack_screen_tile(pl).h == 1 for pl in payloads)


def test_image_payloads_rejects_a_short_buffer():
    with pytest.raises(ValueError, match="needs 153600 RGB565 bytes"):
        s.image_payloads(_blank()[:-2])


def test_image_payloads_rejects_zero_strip_rows():
    with pytest.raises(ValueError, match="strip_rows must be"):
        s.image_payloads(_blank(), strip_rows=0)


def test_offset_tiles_are_placed_at_the_requested_origin():
    payloads = s.image_payloads(_blank(100, 4), w=100, h=4, x0=20, y0=200, strip_rows=2)
    tiles = [p.unpack_screen_tile(pl) for pl in payloads]
    assert [(t.x, t.y, t.w, t.h) for t in tiles] == [(20, 200, 100, 2), (20, 202, 100, 2)]


# ---- text ---------------------------------------------------------------
def test_prepare_text_truncates_at_53_chars_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="kogane.screen"):
        out = s.prepare_text("y" * 60)
    assert out == "y" * 53
    assert "truncated to 53" in caplog.text


def test_prepare_text_does_not_warn_at_exactly_53():
    with caplog_at_warning() as records:
        assert s.prepare_text("z" * 53) == "z" * 53
    assert not records


def test_prepare_text_replaces_unprintables_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="kogane.screen"):
        assert s.prepare_text("caf\u00e9 \u2014 ok") == "caf? ? ok"
    assert "5x7 font" in caplog.text


def test_prepare_text_can_be_quiet():
    with caplog_at_warning() as records:
        assert s.prepare_text("q" * 99, warn=False) == "q" * 53
    assert not records


def test_text_payloads_walk_rows_upward_from_start_row():
    payloads = s.text_payloads(["a", "b", "c"], start_row=3, frame_id=8)
    rows = [p.unpack_screen_text(pl).row for pl in payloads]
    assert rows == [3, 4, 5]
    assert all(p.unpack_screen_header(pl).chunk_cnt == 3 for pl in payloads)
    assert all(p.unpack_screen_header(pl).frame_id == 8 for pl in payloads)


def test_text_payloads_flags():
    payloads = s.text_payloads(["a", "b"], clear=True)
    flags = [p.unpack_screen_header(pl).flags for pl in payloads]
    assert flags == [p.SF_F_FIRST, p.SF_F_LAST]


def test_text_payloads_truncate_rather_than_raise():
    payload = s.text_payloads(["w" * 200], warn=False)[0]
    assert p.unpack_screen_text(payload).text == "w" * 53


def test_text_payloads_drop_lines_past_row_9(caplog):
    with caplog.at_level(logging.WARNING, logger="kogane.screen"):
        payloads = s.text_payloads([f"line{i}" for i in range(14)])
    assert len(payloads) == 10
    assert [p.unpack_screen_text(pl).row for pl in payloads] == list(range(10))
    assert "past row 9" in caplog.text


def test_text_payloads_accepts_a_bare_string():
    assert len(s.text_payloads("hello")) == 1


def test_text_payloads_warns_about_a_scale_the_drone_will_clamp(caplog):
    with caplog.at_level(logging.WARNING, logger="kogane.screen"):
        s.text_payloads(["hi"], scale=4)
    assert "clamped to 3" in caplog.text


def test_text_payloads_carries_the_colours_through():
    payload = s.text_payloads(["x"], fg=p.RGB565_AMBER, bg=p.RGB565_BLUE)[0]
    line = p.unpack_screen_text(payload)
    assert (line.fg, line.bg) == (p.RGB565_AMBER, p.RGB565_BLUE)


# ---- ScreenSender -------------------------------------------------------
def test_sender_sends_every_chunk_as_a_screen_frame():
    sink = ListSink()
    sent = ScreenSender(sink, strip_delay_s=0).send_rgb565(_blank())
    assert sent == 120
    assert [t for t, _ in sink.frames] == [int(p.MsgType.SCREEN_FRAME)] * 120


def test_sender_frame_id_rolls_and_groups_a_frame():
    sink = ListSink()
    sender = ScreenSender(sink, strip_delay_s=0)
    sender.send_text("one")
    sender.send_text("two")
    ids = [p.unpack_screen_header(pl).frame_id for pl in sink.payloads()]
    assert ids == [1, 2]


def test_sender_frame_id_wraps_at_255():
    sender = ScreenSender(ListSink(), strip_delay_s=0)
    sender._frame_id = 255
    assert sender.next_frame_id() == 0


def test_sender_uses_one_frame_id_for_all_strips_of_one_image():
    sink = ListSink()
    ScreenSender(sink, strip_delay_s=0).send_rgb565(_blank())
    ids = {p.unpack_screen_header(pl).frame_id for pl in sink.payloads()}
    assert len(ids) == 1


def test_sender_paces_between_chunks(monkeypatch):
    sink = ListSink()
    sleeps: list[float] = []
    monkeypatch.setattr(s.time, "sleep", sleeps.append)
    ScreenSender(sink, strip_delay_s=0.004).send_rgb565(_blank())
    # 120 chunks, a gap before each one except the first.
    assert len(sleeps) == 119
    assert all(abs(g - 0.004) < 1e-9 for g in sleeps)


def test_sender_release_sets_the_status_flag():
    sink = ListSink()
    ScreenSender(sink, strip_delay_s=0).release()
    hdr = p.unpack_screen_header(sink.payloads()[0])
    assert hdr.flags & p.SF_F_STATUS
    assert len(sink.payloads()[0]) == p.SCREEN_HDR_LEN


def test_sender_counts_chunks():
    sender = ScreenSender(ListSink(), strip_delay_s=0)
    sender.send_text("a")
    sender.send_rgb565(_blank())
    sender.release()
    assert sender.chunks_sent == 1 + 120 + 1


# ---- readout ------------------------------------------------------------
def test_readout_lines_fit_the_panel():
    state = ReadoutState(target_xy=(1.234, 4.567), fresh=True, identity="sujay",
                         link_q=97, batt_mv=11400, drone_xy=(2.0, 2.5), mode="FOLLOW",
                         note="gesture: come here")
    lines = readout_lines(state)
    assert len(lines) <= p.SCREEN_TEXT_ROWS
    for line in lines:
        assert len(line) <= p.SCREEN_TEXT_MAX
        assert all(0x20 <= ord(c) <= 0x7E for c in line)


def test_readout_shows_unknown_fields_as_dashes_not_zeros():
    lines = readout_lines(ReadoutState())
    assert any("--" in ln for ln in lines)
    assert "STALE" in " ".join(lines)
    assert "LINK --" in " ".join(lines)


def test_readout_reports_range_only_when_both_positions_are_known():
    assert ReadoutState(target_xy=(0.0, 0.0)).range_m is None
    assert ReadoutState(drone_xy=(0.0, 0.0)).range_m is None
    assert ReadoutState(target_xy=(3.0, 4.0),
                        drone_xy=(0.0, 0.0)).range_m == pytest.approx(5.0)


def test_readout_lines_are_encodable_as_text_payloads():
    state = ReadoutState(target_xy=(1.0, 2.0), fresh=True, identity="a" * 60, link_q=50)
    for i, line in enumerate(readout_lines(state)):
        p.screen_text_payload(s.prepare_text(line, warn=False), row=i)


# ---- ScreenRenderer -----------------------------------------------------
def test_renderer_is_idle_when_disabled():
    sink = ListSink()
    r = ScreenRenderer(sink, lambda: ReadoutState(), enabled=False)

    async def go():
        task = asyncio.ensure_future(r.run())
        await asyncio.sleep(0.02)
        r.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert sink.frames == []


def test_renderer_pushes_text_rows_when_enabled():
    sink = ListSink()
    state = ReadoutState(target_xy=(1.0, 2.0), fresh=True, identity="sujay", link_q=80,
                         drone_xy=(0.0, 0.0))
    r = ScreenRenderer(sink, lambda: state, enabled=True, mode="text")
    r.sender.strip_delay_s = 0

    sent = asyncio.run(r.push_once())
    assert sent == len(readout_lines(state))
    rows = [p.unpack_screen_text(pl).row for pl in sink.payloads()]
    assert rows == list(range(len(rows)))
    assert all(t == int(p.MsgType.SCREEN_FRAME) for t, _ in sink.frames)
    assert r.updates == 1


def test_renderer_clears_only_on_the_first_update():
    sink = ListSink()
    r = ScreenRenderer(sink, lambda: ReadoutState(), enabled=True, mode="text")
    r.sender.strip_delay_s = 0
    asyncio.run(r.push_once())
    first = [p.unpack_screen_header(pl).flags for pl in sink.payloads()]
    sink.clear()
    asyncio.run(r.push_once())
    second = [p.unpack_screen_header(pl).flags for pl in sink.payloads()]
    assert first[0] & p.SF_F_FIRST
    assert not (second[0] & p.SF_F_FIRST)


def test_renderer_without_a_sink_sends_nothing():
    r = ScreenRenderer(enabled=True)
    assert asyncio.run(r.push_once()) == 0


def test_renderer_attach_wires_a_sink_later():
    r = ScreenRenderer(state=lambda: ReadoutState(), enabled=True, mode="text")
    sink = ListSink()
    r.attach(sink)
    r.sender.strip_delay_s = 0
    assert asyncio.run(r.push_once()) > 0
    assert sink.frames


def test_renderer_release_on_shutdown_hands_the_panel_back():
    sink = ListSink()
    r = ScreenRenderer(sink, lambda: ReadoutState(), enabled=True, mode="text",
                       interval_s=0.01)
    r.sender.strip_delay_s = 0

    async def go():
        task = asyncio.ensure_future(r.run())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    last = sink.payloads()[-1]
    assert p.unpack_screen_header(last).flags & p.SF_F_STATUS


# ---- loopback over a real socket ---------------------------------------
@pytest.fixture()
def loopback():
    """A bound UDP socket plus a sink pointed at it. 127.0.0.1 only, no drone."""
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # A 320x240 frame is 120 x 1312 bytes and the default receive buffer is nowhere near
    # that, so without this the kernel drops datagrams and the test fails for a reason that
    # has nothing to do with the encoder.
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    rx.bind(("127.0.0.1", 0))
    rx.settimeout(3.0)
    sink = SocketSink("127.0.0.1", rx.getsockname()[1])
    try:
        yield rx, sink
    finally:
        sink.close()
        rx.close()


def _drain(rx: socket.socket, expected: int) -> list[p.Frame]:
    out = []
    for _ in range(expected):
        data, _addr = rx.recvfrom(2048)
        frame = p.unpack(data)
        assert frame is not None, "the receiver must accept our own framing"
        out.append(frame)
    return out


def _collect(rx: socket.socket, expected: int):
    """Receive `expected` datagrams on a thread, so a burst cannot outrun the reader."""
    frames: list[p.Frame] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            frames.extend(_drain(rx, expected))
        except BaseException as e:      # surfaced by join() below
            errors.append(e)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def finish() -> list[p.Frame]:
        thread.join(timeout=10.0)
        if errors:
            raise errors[0]
        assert len(frames) == expected, f"got {len(frames)} of {expected} datagrams"
        return frames

    return finish


def test_loopback_text_arrives_as_the_firmware_would_see_it(loopback):
    rx, sink = loopback
    ScreenSender(sink, strip_delay_s=0).send_lines(["KOGANE", "link up"], scale=2,
                                                   fg=p.RGB565_AMBER, clear=True)
    frames = _drain(rx, 2)
    assert [f.msg_type for f in frames] == [int(p.MsgType.SCREEN_FRAME)] * 2
    assert [f.seq for f in frames] == [1, 2]
    lines = [p.unpack_screen_text(f.payload) for f in frames]
    assert [(ln.row, ln.text, ln.scale, ln.fg) for ln in lines] == [
        (0, "KOGANE", 2, p.RGB565_AMBER), (1, "link up", 2, p.RGB565_AMBER)]
    assert p.unpack_screen_header(frames[0].payload).flags & p.SF_F_FIRST
    assert p.unpack_screen_header(frames[1].payload).flags & p.SF_F_LAST


def test_loopback_full_frame_reassembles_to_the_original_pixels(loopback):
    rx, sink = loopback
    rng = np.random.default_rng(11)
    rgb = rng.integers(0, 256, size=(240, 320, 3), dtype=np.uint8)
    original = p.rgb565_bytes(rgb)

    finish = _collect(rx, 120)
    sent = ScreenSender(sink, strip_delay_s=0.0005).send_rgb565(original)
    assert sent == 120

    # Rebuild the panel the way the drone does: blit each tile where it says to go.
    panel = bytearray(len(original))
    for frame in finish():
        assert len(frame.payload) <= 1456          # DISP_CHUNK_MAX on the drone
        tile = p.unpack_screen_tile(frame.payload)
        assert tile is not None
        for r in range(tile.h):
            dst = ((tile.y + r) * 320 + tile.x) * 2
            src = r * tile.w * 2
            panel[dst:dst + tile.w * 2] = tile.pixels[src:src + tile.w * 2]
    assert bytes(panel) == original


def test_loopback_release_is_a_single_status_datagram(loopback):
    rx, sink = loopback
    ScreenSender(sink, strip_delay_s=0).release()
    frame = _drain(rx, 1)[0]
    assert frame.msg_type == int(p.MsgType.SCREEN_FRAME)
    assert len(frame.payload) == p.SCREEN_HDR_LEN
    assert p.unpack_screen_header(frame.payload).flags & p.SF_F_STATUS


# ---- loopback through the real UdpEndpoint ------------------------------
# The SocketSink tests above cover what the CLI does. These cover what the *base station*
# does: EndpointSink on top of the asyncio UdpEndpoint, which is a different transport
# (DatagramTransport.sendto) and a different rolling seq. Still 127.0.0.1 only, no drone.
def _endpoint_loopback(coro_factory, expected: int):
    """Run `coro_factory(sink)` against a bound UdpEndpoint; return the received frames."""
    async def go() -> list[p.Frame]:
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(5.0)
        inbound: list[p.Frame] = []
        # Port 0 so the test never collides with a base station already on udp/5005.
        endpoint = UdpEndpoint(0, lambda f, a: inbound.append(f))
        await endpoint.start()
        try:
            finish = _collect(rx, expected)
            sink = EndpointSink(endpoint, lambda: rx.getsockname())
            await coro_factory(sink)
            # `DatagramTransport.sendto` only queues; on Windows's proactor loop nothing
            # reaches the wire until the coroutine yields. Give the loop a turn before
            # blocking on the reader thread, or a zero-gap send deadlocks the test rather
            # than the encoder. (The renderer always awaits its interval, so this is a
            # property of the harness, not of the sender.)
            await asyncio.sleep(0.2)
            return finish()
        finally:
            endpoint.close()
            rx.close()

    return asyncio.run(go())


def test_udp_endpoint_text_is_byte_for_byte_what_the_firmware_expects():
    async def send(sink):
        await ScreenSender(sink, strip_delay_s=0).asend_lines(
            ["KOGANE", "tracking"], scale=2, fg=p.RGB565_AMBER, clear=True)

    frames = _endpoint_loopback(send, 2)
    assert [f.msg_type for f in frames] == [int(p.MsgType.SCREEN_FRAME)] * 2
    # UdpEndpoint owns its own rolling seq and pre-increments, exactly like SocketSink.
    assert [f.seq for f in frames] == [1, 2]

    first, second = frames
    h0 = p.unpack_screen_header(first.payload)
    h1 = p.unpack_screen_header(second.payload)
    assert (h0.fmt, h0.chunk_idx, h0.chunk_cnt) == (int(p.ScreenFmt.TEXT), 0, 2)
    assert (h1.fmt, h1.chunk_idx, h1.chunk_cnt) == (int(p.ScreenFmt.TEXT), 1, 2)
    assert h0.frame_id == h1.frame_id                     # one logical frame
    assert h0.flags & p.SF_F_FIRST and not h0.flags & p.SF_F_LAST
    assert h1.flags & p.SF_F_LAST and not h1.flags & p.SF_F_FIRST
    assert first.payload[5:8] == b"\x00\x00\x00"          # reserved must be zero

    # Assert the exact bytes rather than the parsed view: sub-header, line header, ASCII.
    assert first.payload[8] == 0 and first.payload[9] == 2
    assert first.payload[10:12] == struct.pack("<H", p.RGB565_AMBER)
    assert first.payload[12:14] == b"\x00\x00"
    assert first.payload[14:] == b"KOGANE"                # not NUL-terminated
    assert second.payload[8] == 1 and second.payload[14:] == b"tracking"


def test_udp_endpoint_full_frame_is_120_valid_strips():
    rgb = np.random.default_rng(23).integers(0, 256, size=(240, 320, 3), dtype=np.uint8)
    original = p.rgb565_bytes(rgb)

    async def send(sink):
        assert await ScreenSender(sink, strip_delay_s=0.0005).asend_rgb565(original) == 120

    frames = _endpoint_loopback(send, 120)
    panel = bytearray(len(original))
    for i, frame in enumerate(frames):
        # 14 KGN header + 8 sub-header + 8 tile header + 1280 px + 2 crc = 1312 on the wire.
        assert len(frame.payload) == 8 + 8 + 1280
        hdr = p.unpack_screen_header(frame.payload)
        assert (hdr.chunk_idx, hdr.chunk_cnt) == (i, 120)
        assert bool(hdr.flags & p.SF_F_FIRST) == (i == 0)
        assert bool(hdr.flags & p.SF_F_LAST) == (i == 119)
        tile = p.unpack_screen_tile(frame.payload)
        assert (tile.x, tile.y, tile.w, tile.h) == (0, i * 2, 320, 2)
        panel[tile.y * 320 * 2:(tile.y + 2) * 320 * 2] = tile.pixels
    assert bytes(panel) == original
    assert len({p.unpack_screen_header(f.payload).frame_id for f in frames}) == 1


def test_udp_endpoint_renderer_push_reaches_the_wire():
    """The whole base-station chain: state snapshot -> text rows -> real datagrams."""
    state = ReadoutState(target_xy=(1.5, 3.25), fresh=True, identity="sujay", link_q=88,
                         batt_mv=11400, drone_xy=(2.0, 1.0), mode="FOLLOW")
    rows = len(readout_lines(state))

    async def send(sink):
        r = ScreenRenderer(sink, lambda: state, enabled=True, mode="text")
        assert await r.push_once() == rows

    frames = _endpoint_loopback(send, rows)
    lines = [p.unpack_screen_text(f.payload) for f in frames]
    assert [ln.row for ln in lines] == list(range(rows))
    assert all(len(ln.text) <= p.SCREEN_TEXT_MAX for ln in lines)
    assert any("sujay" in ln.text for ln in lines)
    assert any("88" in ln.text for ln in lines)


def test_udp_endpoint_send_before_start_is_a_silent_no_op():
    """No transport yet -> UdpEndpoint drops the send. The renderer must not raise."""
    endpoint = UdpEndpoint(0, lambda f, a: None)
    sink = EndpointSink(endpoint, ("127.0.0.1", 5005))
    ScreenSender(sink, strip_delay_s=0).send_text("no transport yet")
    ScreenSender(sink, strip_delay_s=0).release()


def test_udp_endpoint_survives_an_unreachable_destination():
    """A drone that is not listening must not kill the stream. Sends still complete."""
    async def go() -> int:
        endpoint = UdpEndpoint(0, lambda f, a: None)
        await endpoint.start()
        try:
            # 127.0.0.1 on a port nothing is bound to: an ICMP port-unreachable comes back.
            sink = EndpointSink(endpoint, ("127.0.0.1", 9))
            sender = ScreenSender(sink, strip_delay_s=0)
            for _ in range(3):
                await sender.asend_lines(["still going"])
            sender.release()
            return sender.chunks_sent
        finally:
            endpoint.close()

    assert asyncio.run(go()) == 4


# ---- helper -------------------------------------------------------------
class caplog_at_warning:
    """Capture WARNING records from the screen logger without pytest's caplog fixture."""

    def __enter__(self) -> list[logging.LogRecord]:
        self.records: list[logging.LogRecord] = []
        self.handler = _Collector(self.records)
        self.logger = logging.getLogger("kogane.screen")
        self.prev = self.logger.level
        self.logger.setLevel(logging.WARNING)
        self.logger.addHandler(self.handler)
        return self.records

    def __exit__(self, *exc) -> None:
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.prev)


class _Collector(logging.Handler):
    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__(level=logging.WARNING)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)
