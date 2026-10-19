"""BaseStation wiring for the screen and audio paths.

Covers the bits that live in main.py rather than in the senders: the AUDIO_MIC receive
branch in `_on_frame`, the readout snapshot the screen task pulls, and the fact that none of
this disturbs the control loop or the existing dispatch. No sockets are bound and no drone is
involved — frames are handed to `_on_frame` directly, exactly as `test_control_loop.py` does.
"""
from __future__ import annotations

import struct

import pytest

from kogane_base import protocol as p
from kogane_base.main import BaseStation
from kogane_base.net.sink import ListSink


def _frame(msg_type, payload: bytes, seq: int = 1, src_id: int = 0) -> p.Frame:
    return p.Frame(int(msg_type), seq, src_id, payload)


# ---- AUDIO_MIC receive path ---------------------------------------------
def test_audio_mic_chunks_are_decoded_into_the_recorder():
    bs = BaseStation()
    pcm = struct.pack("<4h", 10, -20, 30, -40)
    bs._on_frame(_frame(p.MsgType.AUDIO_MIC, p.audio_pcm_payload(pcm, 0, p.AU_F_START)),
                 ("10.28.43.18", 5005))
    assert bs.mic.pcm == pcm
    assert bs.mic.stats.chunks == 1
    assert bs.mic.stats.streams == 1


def test_audio_mic_learns_the_drone_address():
    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.AUDIO_MIC,
                        p.audio_pcm_payload(b"\x00\x00", 0, p.AU_F_START)),
                 ("10.28.43.18", 5005))
    assert bs._drone_addr == ("10.28.43.18", 5005)


def test_malformed_audio_mic_is_counted_and_does_not_move_the_address():
    bs = BaseStation()
    before = bs._drone_addr
    bs._on_frame(_frame(p.MsgType.AUDIO_MIC, b"\x01\x00\x00"), ("10.28.43.18", 5005))
    assert bs.mic.stats.malformed == 1
    assert bs.mic.pcm == b""
    assert bs._drone_addr == before


def test_audio_mic_does_not_count_as_a_target_measurement():
    """Hearing someone says nothing about where they are."""
    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.AUDIO_MIC,
                        p.audio_pcm_payload(b"\x11\x11" * 512, 0, p.AU_F_START)),
                 ("1.2.3.4", 5005))
    assert bs.freshness.last_t is None
    assert not bs.filter.initialised


def test_a_ctrl_chunk_arriving_on_audio_mic_is_ignored():
    """PROTOCOL.md: CTRL is base -> drone by definition; on 0x41 it is meaningless."""
    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.AUDIO_MIC,
                        p.audio_ctrl_payload(p.AudioCmd.MIC_ON)), ("1.2.3.4", 5005))
    assert bs.mic.pcm == b""
    assert bs.mic.stats.malformed == 1


def test_mic_stream_gaps_are_reported_not_hidden():
    bs = BaseStation()
    for seq in (0, 1, 5):
        bs._on_frame(_frame(p.MsgType.AUDIO_MIC,
                            p.audio_pcm_payload(b"\x00\x00" * 512, seq,
                                                p.AU_F_START if seq == 0 else 0)),
                     ("1.2.3.4", 5005))
    assert bs.mic.stats.gaps == 1
    assert bs.mic.stats.lost_chunks == 3
    assert bs.mic.stats.chunks == 3


# ---- drone_state validity bits ------------------------------------------
def test_link_quality_is_only_taken_when_the_drone_says_it_is_valid():
    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 0, 0, 97)), ("1.2.3.4", 5005))
    assert bs.screen_state().link_q is None, "a clear validity bit means no data"

    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 0, p.DS_F_LINKQ_VALID, 97)),
                 ("1.2.3.4", 5005))
    assert bs.screen_state().link_q == 97


def test_battery_is_only_taken_when_valid():
    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 11400, 0, 0)), ("1.2.3.4", 5005))
    assert bs.screen_state().batt_mv is None

    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 11400, p.DS_F_BATT_VALID, 0)),
                 ("1.2.3.4", 5005))
    assert bs.screen_state().batt_mv == 11400


def test_heading_only_state_does_not_overwrite_position():
    bs = BaseStation()
    initial = bs.drone_xy
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(150, -250, 0, 0, 0, 0, 0)), ("1.2.3.4", 5005))
    assert bs.drone_xy == initial
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(150, -250, 0, 0, 0, p.DS_F_POS_VALID, 0)),
                 ("1.2.3.4", 5005))
    assert bs.drone_xy == pytest.approx((1.5, -2.5))


def test_expired_telemetry_clears_battery_and_link_readout():
    bs = BaseStation()
    flags = p.DS_F_BATT_VALID | p.DS_F_LINKQ_VALID
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 4980, flags, 90)),
                 ("1.2.3.4", 5005))
    assert bs.screen_state().batt_mv == 4980
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(0, 0, 0, 0, 0, 0, 0)),
                 ("1.2.3.4", 5005))
    assert bs.screen_state().batt_mv is None
    assert bs.screen_state().link_q is None


# ---- readout snapshot ---------------------------------------------------
def test_screen_state_starts_with_nothing_known():
    st = BaseStation().screen_state()
    assert st.target_xy is None
    assert st.fresh is False
    assert st.identity is None
    assert st.link_q is None and st.batt_mv is None
    assert st.drone_xy is not None          # seeded to the room centre


def test_screen_state_reports_a_tracked_target():
    import time

    bs = BaseStation()
    payload = bytes([1]) + struct.pack("<hhhH", 1000, 2000, 0, 100)
    bs._on_frame(_frame(p.MsgType.MMWAVE_TARGETS, payload), ("1.2.3.4", 5005))
    st = bs.screen_state()
    assert st.fresh is True
    assert st.target_xy is not None
    assert bs.freshness.fresh(time.monotonic())


def test_screen_state_trail_grows_while_fresh_and_stays_bounded():
    bs = BaseStation()
    payload = bytes([1]) + struct.pack("<hhhH", 1000, 2000, 0, 100)
    bs._on_frame(_frame(p.MsgType.MMWAVE_TARGETS, payload), ("1.2.3.4", 5005))
    for _ in range(200):
        bs.screen_state()
    assert len(bs.screen_state().trail) <= 48


def test_screen_state_lines_all_fit_the_panel():
    from kogane_base.screen.frames import readout_lines

    bs = BaseStation()
    bs._on_frame(_frame(p.MsgType.MMWAVE_TARGETS,
                        bytes([1]) + struct.pack("<hhhH", 1200, 2400, 45, 100)),
                 ("1.2.3.4", 5005))
    bs._on_frame(_frame(p.MsgType.DRONE_STATE,
                        p.pack_drone_state(80, 120, 150, 0, 11400,
                                           p.DS_F_LINKQ_VALID | p.DS_F_BATT_VALID, 91)),
                 ("1.2.3.4", 5005))
    lines = readout_lines(bs.screen_state())
    assert 0 < len(lines) <= p.SCREEN_TEXT_ROWS
    for i, line in enumerate(lines):
        p.screen_text_payload(line, row=i)      # raises if it would not fit the wire


# ---- the screen task is wired but silent by default --------------------
def test_screen_renderer_is_attached_to_the_udp_endpoint():
    bs = BaseStation()
    assert bs.screen.sink is not None
    assert bs.screen.state is not None
    # The sink follows the learned drone address rather than freezing it.
    before = bs.screen.sink.addr
    bs._on_frame(_frame(p.MsgType.HEARTBEAT, p.pack_heartbeat(1, p.Role.DRONE)),
                 ("10.28.43.18", 5005))
    assert bs.screen.sink.addr == ("10.28.43.18", 5005) != before


def test_screen_renderer_is_off_unless_configured(monkeypatch):
    from kogane_base.config import CONFIG

    assert CONFIG.screen_enabled is False, "the live readout must not fight a manual demo"
    assert BaseStation().screen.enabled is False


def test_screen_push_sends_screen_frames_when_enabled():
    import asyncio

    bs = BaseStation()
    sink = ListSink()
    bs.screen.attach(sink)
    bs.screen.enabled = True
    bs.screen.sender.strip_delay_s = 0
    sent = asyncio.run(bs.screen.push_once())
    assert sent > 0
    assert all(t == int(p.MsgType.SCREEN_FRAME) for t, _ in sink.frames)
