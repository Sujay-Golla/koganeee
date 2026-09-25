"""Tests for kogane_base.audio.sender / recorder, plus a real loopback socket.

The pacing tests replace `time.sleep` so they assert the *schedule* rather than waiting for
it. The loopback tests bind a UDP socket on 127.0.0.1 so the whole encode path runs for real
— payload build, KGN framing, CRC, sendto, recvfrom, unpack — with no drone and no audio
hardware anywhere.
"""
from __future__ import annotations

import asyncio
import socket
import struct

import numpy as np
import pytest

from kogane_base import protocol as p
from kogane_base.audio import sender as snd
from kogane_base.audio.recorder import MicRecorder
from kogane_base.audio.sender import AudioSender, pcm_payloads
from kogane_base.audio.wav import tone
from kogane_base.net.sink import ListSink, SocketSink


def _silence(samples: int) -> bytes:
    return b"\x00" * (samples * 2)


# ---- pure payload building ----------------------------------------------
def test_payloads_carry_start_on_the_first_and_end_on_the_last():
    payloads = pcm_payloads(_silence(1000), chunk_bytes=640)
    assert len(payloads) == 4                      # 2000 bytes / 640 -> 640,640,640,80
    flags = [p.unpack_audio_header(pl).flags for pl in payloads]
    assert flags == [p.AU_F_START, 0, 0, p.AU_F_END]


def test_a_single_chunk_utterance_carries_both_flags():
    payloads = pcm_payloads(_silence(10), chunk_bytes=640)
    assert len(payloads) == 1
    assert p.unpack_audio_header(payloads[0]).flags == p.AU_F_START | p.AU_F_END


def test_payload_seq_counts_up_from_start_seq():
    payloads = pcm_payloads(_silence(1000), chunk_bytes=640, start_seq=7)
    assert [p.unpack_audio_header(pl).seq for pl in payloads] == [7, 8, 9, 10]


def test_payload_seq_wraps_at_a_u16():
    payloads = pcm_payloads(_silence(1000), chunk_bytes=640, start_seq=65534)
    assert [p.unpack_audio_header(pl).seq for pl in payloads] == [65534, 65535, 0, 1]


def test_payloads_can_omit_the_flags_for_a_continuation():
    payloads = pcm_payloads(_silence(1000), chunk_bytes=640, start=False, end=False)
    assert all(p.unpack_audio_header(pl).flags == 0 for pl in payloads)


def test_every_payload_is_within_the_wire_cap():
    payloads = pcm_payloads(_silence(50000), chunk_bytes=p.AUDIO_PCM_MAX_BYTES)
    for pl in payloads:
        body = pl[p.AUDIO_HDR_LEN:]
        assert 0 < len(body) <= p.AUDIO_PCM_MAX_BYTES
        assert len(body) % 2 == 0
        assert len(p.pack(p.MsgType.AUDIO_TTS, pl)) + 28 <= 1500


def test_payloads_reconstruct_the_original_pcm_in_order():
    original = tone(440, 0.3)
    joined = b"".join(pl[p.AUDIO_HDR_LEN:]
                      for pl in pcm_payloads(original.tobytes(), chunk_bytes=640))
    assert joined == original.tobytes()


# ---- AudioSender geometry ----------------------------------------------
def test_default_chunk_is_20ms_320_samples_640_bytes():
    s = AudioSender(ListSink(), chunk_ms=20.0)
    assert s.chunk_samples == 320
    assert s.chunk_bytes == 640
    assert s.chunk_s == pytest.approx(0.02)


def test_45ms_is_the_largest_chunk_the_sender_will_accept():
    assert AudioSender(ListSink(), chunk_ms=45.0).chunk_bytes == 1440
    with pytest.raises(ValueError, match="drops anything over 1440"):
        AudioSender(ListSink(), chunk_ms=46.0)


def test_a_lead_larger_than_the_drone_queue_warns(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="kogane.audio"):
        AudioSender(ListSink(), chunk_ms=20.0, lead_ms=400.0)   # 20 chunks vs a queue of 12
    assert "drops the oldest" in caplog.text


# ---- CTRL ---------------------------------------------------------------
@pytest.mark.parametrize("call,cmd", [
    ("mic_on", p.AudioCmd.MIC_ON),
    ("mic_off", p.AudioCmd.MIC_OFF),
    ("selftest", p.AudioCmd.SELFTEST),
    ("flush", p.AudioCmd.FLUSH),
])
def test_ctrl_helpers_send_the_right_command(call, cmd):
    sink = ListSink()
    getattr(AudioSender(sink), call)()
    assert len(sink.frames) == 1
    msg_type, payload = sink.frames[0]
    assert msg_type == int(p.MsgType.AUDIO_TTS)     # CTRL rides inside 0x40, not 0x41
    chunk = p.unpack_audio_chunk(payload)
    assert chunk is not None
    assert chunk.fmt == p.AudioFmt.CTRL
    assert chunk.cmd == int(cmd)


def test_ctrl_does_not_advance_the_pcm_stream_sequence():
    sink = ListSink()
    s = AudioSender(sink, chunk_ms=20.0)
    s.mic_on()
    s.flush()
    s.stream_pcm(_silence(320), realtime=False)
    pcm = [pl for _, pl in sink.frames if pl[0] == int(p.AudioFmt.PCM_S16LE)]
    assert p.unpack_audio_header(pcm[0]).seq == 0


# ---- streaming ----------------------------------------------------------
def test_stream_pcm_sends_every_chunk_as_audio_tts():
    sink = ListSink()
    sent = AudioSender(sink, chunk_ms=20.0).stream_pcm(tone(440, 1.0), realtime=False)
    assert sent == 50                               # 1 s / 20 ms
    assert all(t == int(p.MsgType.AUDIO_TTS) for t, _ in sink.frames)


def test_stream_pcm_accepts_bytes_or_an_array():
    a, b = ListSink(), ListSink()
    pcm = tone(440, 0.1)
    AudioSender(a, chunk_ms=20.0).stream_pcm(pcm, realtime=False)
    AudioSender(b, chunk_ms=20.0).stream_pcm(pcm.tobytes(), realtime=False)
    assert a.frames == b.frames


def test_stream_pcm_restarts_seq_at_zero_for_each_utterance():
    sink = ListSink()
    s = AudioSender(sink, chunk_ms=20.0)
    s.stream_pcm(_silence(960), realtime=False)      # 3 chunks
    s.stream_pcm(_silence(640), realtime=False)      # 2 chunks
    seqs = [p.unpack_audio_header(pl).seq for pl in sink.payloads()]
    assert seqs == [0, 1, 2, 0, 1]


def test_paced_streaming_schedules_one_chunk_per_chunk_duration(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(snd.time, "sleep", sleeps.append)
    # Frozen clock: every requested sleep is the full outstanding interval.
    monkeypatch.setattr(snd.time, "monotonic", lambda: 0.0)

    s = AudioSender(ListSink(), chunk_ms=20.0, lead_ms=120.0)
    s.stream_pcm(_silence(320 * 10), realtime=True)

    # First six chunks are inside the 120 ms lead, so no sleep; after that one sleep each.
    assert len(sleeps) == 4
    assert sleeps == pytest.approx([0.02, 0.04, 0.06, 0.08], abs=1e-9)


def test_unpaced_streaming_never_sleeps(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(snd.time, "sleep", sleeps.append)
    AudioSender(ListSink(), chunk_ms=20.0).stream_pcm(_silence(3200), realtime=False)
    assert sleeps == []


def test_paced_streaming_really_takes_about_real_time():
    """Sleeps for real. 0.3 s of audio must take roughly 0.3 s minus the lead to send."""
    import time
    s = AudioSender(ListSink(), chunk_ms=20.0, lead_ms=60.0)
    t0 = time.monotonic()
    s.stream_pcm(tone(440, 0.3), realtime=True)
    elapsed = time.monotonic() - t0
    assert 0.15 < elapsed < 0.8


def test_progress_callback_reports_index_and_total():
    seen: list[tuple[int, int]] = []
    AudioSender(ListSink(), chunk_ms=20.0).stream_pcm(
        _silence(960), realtime=False, on_progress=lambda i, n: seen.append((i, n)))
    assert seen == [(0, 3), (1, 3), (2, 3)]


def test_send_tone_and_send_silence_produce_audio_chunks():
    sink = ListSink()
    s = AudioSender(sink, chunk_ms=20.0)
    assert s.send_tone(880, 0.1, realtime=False) == 5
    assert s.send_silence(0.04, realtime=False) == 2
    assert s.chunks_sent == 7


def test_send_wav_converts_and_streams(tmp_path):
    from kogane_base.audio.wav import write_wav

    path = write_wav(tmp_path / "t.wav", tone(440, 0.2))
    sink = ListSink()
    sent = AudioSender(sink, chunk_ms=20.0).send_wav(path, realtime=False)
    assert sent == 10
    joined = b"".join(pl[p.AUDIO_HDR_LEN:] for pl in sink.payloads())
    assert joined == tone(440, 0.2).tobytes()


def test_async_streaming_matches_the_sync_path():
    a, b = ListSink(), ListSink()
    AudioSender(a, chunk_ms=20.0).stream_pcm(_silence(960), realtime=False)
    asyncio.run(AudioSender(b, chunk_ms=20.0).astream_pcm(_silence(960), realtime=False))
    assert a.frames == b.frames


# ---- MicRecorder --------------------------------------------------------
def _mic_payload(pcm: bytes, seq: int, flags: int = 0) -> bytes:
    return p.audio_pcm_payload(pcm, seq=seq, flags=flags)


def test_recorder_accumulates_pcm_in_order():
    rec = MicRecorder()
    a = struct.pack("<2h", 1, 2)
    b = struct.pack("<2h", 3, 4)
    rec.on_payload(_mic_payload(a, 0, p.AU_F_START))
    rec.on_payload(_mic_payload(b, 1, p.AU_F_END))
    assert rec.pcm == a + b
    assert rec.stats.chunks == 2
    assert rec.stats.samples == 4
    assert rec.stats.streams == 1
    assert rec.stats.ended == 1
    assert rec.stats.gaps == 0


def test_recorder_counts_a_sequence_gap_without_concealing_it():
    rec = MicRecorder()
    rec.on_payload(_mic_payload(b"\x00\x00", 0, p.AU_F_START))
    rec.on_payload(_mic_payload(b"\x00\x00", 4))       # 1, 2, 3 missing
    assert rec.stats.gaps == 1
    assert rec.stats.lost_chunks == 3
    assert rec.stats.samples == 2                     # nothing invented to fill the hole


def test_recorder_ignores_an_absurd_sequence_jump():
    rec = MicRecorder()
    rec.on_payload(_mic_payload(b"\x00\x00", 0, p.AU_F_START))
    rec.on_payload(_mic_payload(b"\x00\x00", 50000))
    assert rec.stats.gaps == 0                        # a restart, not 50000 lost chunks


def test_recorder_start_flag_resets_the_gap_tracking():
    rec = MicRecorder()
    rec.on_payload(_mic_payload(b"\x00\x00", 10, p.AU_F_START))
    rec.on_payload(_mic_payload(b"\x00\x00", 0, p.AU_F_START))
    assert rec.stats.gaps == 0
    assert rec.stats.streams == 2


def test_recorder_rejects_malformed_and_ctrl_chunks():
    rec = MicRecorder()
    assert rec.on_payload(b"\x01\x00") is None                       # short
    assert rec.on_payload(p.pack_audio_header(1) + b"\x00") is None   # odd body
    assert rec.on_payload(p.audio_ctrl_payload(p.AudioCmd.MIC_ON)) is None
    assert rec.stats.malformed == 3
    assert rec.pcm == b""


def test_recorder_tracks_the_peak_level():
    rec = MicRecorder()
    rec.on_payload(_mic_payload(struct.pack("<3h", 100, -9000, 40), 0, p.AU_F_START))
    assert rec.stats.peak == 9000


def test_recorder_buffer_is_bounded_and_keeps_the_newest_audio():
    rec = MicRecorder(max_seconds=0.001)              # 16 samples
    for seq in range(5):
        rec.on_payload(_mic_payload(struct.pack("<8h", *([seq] * 8)), seq,
                                    p.AU_F_START if seq == 0 else 0))
    assert len(rec.pcm) == 32                         # 16 samples
    tail = np.frombuffer(rec.pcm, dtype="<i2")
    assert set(tail.tolist()) == {3, 4}               # the oldest chunks were dropped
    assert rec.stats.trimmed_samples == 24


def test_recorder_duration_and_reset():
    """One second of audio arrives as 32 x 512-sample blocks, the drone's own block size."""
    rec = MicRecorder()
    for seq in range(31):     # 31 * 512 = 15872 samples
        rec.on_payload(_mic_payload(_silence(p.AUDIO_MIC_BLOCK_SAMPLES), seq,
                                    p.AU_F_START if seq == 0 else 0))
    rec.on_payload(_mic_payload(_silence(128), 31, p.AU_F_END))
    assert rec.stats.samples == 16000
    assert rec.buffered_s == pytest.approx(1.0)
    assert rec.stats.duration_s == pytest.approx(1.0)
    rec.reset()
    assert rec.pcm == b"" and rec.stats.chunks == 0


def test_recorder_writes_a_16k_mono_wav(tmp_path):
    from kogane_base.audio.wav import wav_probe

    rec = MicRecorder()
    original = tone(440, 0.2)
    rec.on_payload(_mic_payload(original.tobytes()[:1024], 0, p.AU_F_START))
    out = rec.write_wav(tmp_path / "mic.wav")
    assert out is not None
    info = wav_probe(out)
    assert (info.rate, info.channels, info.sample_width) == (16000, 1, 2)
    assert info.frames == 512


def test_recorder_write_wav_returns_none_with_nothing_buffered(tmp_path):
    assert MicRecorder().write_wav(tmp_path / "empty.wav") is None


def test_recorder_write_wav_writes_nothing_without_a_configured_path(monkeypatch):
    """No path, no file. A mic on an aircraft must not leave recordings behind by default."""
    from kogane_base.config import CONFIG

    monkeypatch.setattr(CONFIG, "mic_wav_path", "")
    rec = MicRecorder()
    rec.on_payload(_mic_payload(b"\x00\x00", 0, p.AU_F_START))
    assert rec.write_wav() is None


# ---- loopback over a real socket ---------------------------------------
@pytest.fixture()
def loopback():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
        assert frame is not None
        out.append(frame)
    return out


def test_loopback_ctrl_selftest(loopback):
    rx, sink = loopback
    AudioSender(sink).selftest()
    frame = _drain(rx, 1)[0]
    assert frame.msg_type == int(p.MsgType.AUDIO_TTS)
    assert len(frame.payload) == 5
    chunk = p.unpack_audio_chunk(frame.payload)
    assert chunk.fmt == p.AudioFmt.CTRL and chunk.cmd == int(p.AudioCmd.SELFTEST)


def test_loopback_pcm_reassembles_to_the_original_audio(loopback):
    rx, sink = loopback
    original = tone(660, 0.4)
    sent = AudioSender(sink, chunk_ms=20.0).stream_pcm(original, realtime=False)
    assert sent == 20

    frames = _drain(rx, 20)
    assert [f.seq for f in frames] == list(range(1, 21))     # header seq, per-datagram
    chunks = [p.unpack_audio_chunk(f.payload) for f in frames]
    assert all(c is not None for c in chunks)
    assert [c.seq for c in chunks] == list(range(20))        # stream seq, per-utterance
    assert chunks[0].start and not chunks[0].end
    assert chunks[-1].end and not chunks[-1].start
    assert all(not (c.start or c.end) for c in chunks[1:-1])
    assert b"".join(c.pcm for c in chunks) == original.tobytes()


def test_loopback_mic_path_end_to_end(loopback):
    """Round-trip the drone's own direction: 0x41 in, WAV-able PCM out."""
    rx, sink = loopback
    original = tone(880, 0.32)                    # 10 x 512-sample blocks
    blocks = [original.tobytes()[i:i + 1024]
              for i in range(0, len(original.tobytes()), 1024)]
    for i, block in enumerate(blocks):
        flags = (p.AU_F_START if i == 0 else 0) | (p.AU_F_END if i == len(blocks) - 1
                                                   else 0)
        sink.send(p.MsgType.AUDIO_MIC, p.audio_pcm_payload(block, seq=i, flags=flags))

    rec = MicRecorder()
    for frame in _drain(rx, len(blocks)):
        assert frame.msg_type == int(p.MsgType.AUDIO_MIC)
        assert len(frame.payload) - p.AUDIO_HDR_LEN == 1024   # a 1044-byte datagram
        assert rec.on_payload(frame.payload) is not None
    assert rec.pcm == original.tobytes()
    assert rec.stats.gaps == 0
    assert rec.stats.streams == 1 and rec.stats.ended == 1
    assert rec.buffered_s == pytest.approx(0.32)


def test_socket_sink_does_not_bind_unless_asked():
    """A send-only tool must not take the KGN port off a base station on the same host."""
    s = SocketSink("127.0.0.1", 45099)
    try:
        assert s.bound_port is None
    finally:
        s.close()


def test_socket_sink_binds_the_base_port_not_the_destination_port():
    """The drone sends AUDIO_MIC to a *configured* base address (wifi_udp.c), so the
    receive port is ours, not the one we send to."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    free = probe.getsockname()[1]
    probe.close()

    s = SocketSink("127.0.0.1", 45098, recv=True, bind_port=free)
    try:
        assert s.bound_port == free
        assert s.sock.getsockname()[1] == free
        assert s.addr == ("127.0.0.1", 45098)
    finally:
        s.close()


def test_loopback_mic_arrives_on_the_bound_base_port():
    """End to end on the receive side: bind a base port, have a 'drone' send 0x41 there."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    base_port = probe.getsockname()[1]
    probe.close()

    sink = SocketSink("127.0.0.1", base_port, recv=True, bind_port=base_port)
    drone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sink.sock.settimeout(2.0)
        original = tone(880, 0.064).tobytes()          # two 512-sample blocks
        blocks = [original[:1024], original[1024:]]
        for i, block in enumerate(blocks):
            flags = (p.AU_F_START if i == 0 else 0) | (p.AU_F_END if i else 0)
            drone.sendto(p.pack(p.MsgType.AUDIO_MIC,
                                p.audio_pcm_payload(block, i, flags), i),
                         ("127.0.0.1", base_port))

        rec = MicRecorder()
        for _ in blocks:
            data, _addr = sink.sock.recvfrom(2048)
            frame = p.unpack(data)
            assert frame is not None and frame.msg_type == int(p.MsgType.AUDIO_MIC)
            assert rec.on_payload(frame.payload) is not None
        assert rec.pcm == original
        assert rec.stats.streams == 1 and rec.stats.ended == 1 and rec.stats.gaps == 0
    finally:
        drone.close()
        sink.close()
