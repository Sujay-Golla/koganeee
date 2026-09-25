"""Wire-format tests for audio_chunk (0x40 AUDIO_TTS / 0x41 AUDIO_MIC).

Pinned against the offset table in firmware/shared/PROTOCOL.md §1 and the acceptance rules
in companion-esp32s3/main/audio_i2s.c. No sockets, no audio hardware.
"""
from __future__ import annotations

import struct

import pytest

from kogane_base import protocol as p


# ---- the format is fixed, not negotiated ----------------------------------
def test_pcm_format_constants():
    assert p.AUDIO_RATE_HZ == 16000
    assert p.AUDIO_SAMPLE_WIDTH == 2
    assert p.AUDIO_CHANNELS == 1


def test_chunk_budget_is_1440_bytes_720_samples_45ms():
    # 1500 MTU - 28 IP/UDP - 14 KGN header - 2 crc - 4 sub-header = 1452, capped at 1440.
    assert p.AUDIO_PCM_MAX_BYTES == 1440
    assert p.AUDIO_PCM_MAX_SAMPLES == 720
    assert p.AUDIO_PCM_MAX_SAMPLES / p.AUDIO_RATE_HZ == pytest.approx(0.045)


def test_drone_queue_depth_and_mic_block_are_recorded():
    assert p.AUDIO_TTS_QUEUE_DEPTH == 12
    assert p.AUDIO_MIC_BLOCK_SAMPLES == 512      # 32 ms, a 1024-byte body


def test_audio_enum_and_flag_values():
    assert (p.AudioFmt.PCM_S16LE, p.AudioFmt.CTRL) == (1, 2)
    assert [p.AudioCmd.MIC_ON, p.AudioCmd.MIC_OFF, p.AudioCmd.SELFTEST,
            p.AudioCmd.FLUSH] == [1, 2, 3, 4]
    assert (p.AU_F_START, p.AU_F_END) == (0x01, 0x02)


# ---- sub-header byte layout ----------------------------------------------
def test_audio_sub_header_len_is_4():
    assert p.AUDIO_HDR_LEN == 4


def test_audio_sub_header_field_offsets():
    hdr = p.pack_audio_header(p.AudioFmt.PCM_S16LE, p.AU_F_START | p.AU_F_END, 0xBEEF)
    assert len(hdr) == 4
    assert hdr[0] == 1                             # 0 fmt
    assert hdr[1] == 0x03                          # 1 flags
    assert hdr[2:4] == struct.pack("<H", 0xBEEF)   # 2 seq (LE u16)


def test_audio_sub_header_keeps_pcm_two_byte_aligned():
    """The 4-byte size exists so both ends can cast the body to int16 in place."""
    assert p.AUDIO_HDR_LEN % 2 == 0


def test_audio_seq_wraps_at_a_u16():
    assert p.pack_audio_header(1, 0, 0x10000)[2:4] == struct.pack("<H", 0)
    assert p.pack_audio_header(1, 0, 65535)[2:4] == b"\xff\xff"


def test_unpack_audio_header_roundtrip_and_short_reject():
    hdr = p.pack_audio_header(2, p.AU_F_END, 7)
    assert p.unpack_audio_header(hdr) == p.AudioHeader(2, p.AU_F_END, 7)
    assert p.unpack_audio_header(hdr[:3]) is None


# ---- fmt = 1 PCM ---------------------------------------------------------
def test_pcm_payload_layout():
    pcm = struct.pack("<4h", 0, 1000, -1000, 32767)
    payload = p.audio_pcm_payload(pcm, seq=5, flags=p.AU_F_START)
    assert payload[0] == int(p.AudioFmt.PCM_S16LE)
    assert payload[1] == p.AU_F_START
    assert payload[2:4] == struct.pack("<H", 5)
    assert payload[4:] == pcm                       # offset 4 samples
    assert len(payload) == 4 + 8


def test_pcm_payload_at_the_exact_cap_is_accepted():
    payload = p.audio_pcm_payload(b"\x00" * p.AUDIO_PCM_MAX_BYTES)
    assert len(payload) == 4 + 1440
    # 14 header + 4 sub + 1440 + 2 crc = 1460; + 28 IP/UDP = 1488, inside the MTU.
    assert len(p.pack(p.MsgType.AUDIO_TTS, payload)) == 1460
    assert len(p.pack(p.MsgType.AUDIO_TTS, payload)) + 28 < 1500


def test_pcm_payload_over_the_cap_is_rejected():
    with pytest.raises(ValueError, match="drops anything over 1440"):
        p.audio_pcm_payload(b"\x00" * (p.AUDIO_PCM_MAX_BYTES + 2))


def test_pcm_payload_rejects_an_odd_body():
    with pytest.raises(ValueError, match="whole int16 samples"):
        p.audio_pcm_payload(b"\x00" * 641)


def test_pcm_payload_rejects_an_empty_body():
    with pytest.raises(ValueError, match="empty PCM chunk"):
        p.audio_pcm_payload(b"")


def test_pcm_roundtrip_through_a_full_datagram():
    pcm = struct.pack("<320h", *range(320))
    payload = p.audio_pcm_payload(pcm, seq=9, flags=p.AU_F_END)
    frame = p.unpack(p.pack(p.MsgType.AUDIO_TTS, payload, seq=3))
    assert frame is not None
    assert frame.msg_type == p.MsgType.AUDIO_TTS
    chunk = p.unpack_audio_chunk(frame.payload)
    assert chunk is not None
    assert chunk.fmt == p.AudioFmt.PCM_S16LE
    assert chunk.seq == 9
    assert chunk.pcm == pcm
    assert chunk.cmd is None
    assert chunk.end and not chunk.start
    assert chunk.samples == 320
    assert chunk.duration_s == pytest.approx(0.02)


# ---- fmt = 2 CTRL --------------------------------------------------------
@pytest.mark.parametrize("cmd,value", [
    (p.AudioCmd.MIC_ON, 1), (p.AudioCmd.MIC_OFF, 2),
    (p.AudioCmd.SELFTEST, 3), (p.AudioCmd.FLUSH, 4),
])
def test_ctrl_payload_layout(cmd, value):
    payload = p.audio_ctrl_payload(cmd)
    assert len(payload) == 5
    assert payload[0] == int(p.AudioFmt.CTRL)
    assert payload[1] == 0
    assert payload[2:4] == struct.pack("<H", 0)
    assert payload[4] == value                      # offset 4 cmd


def test_ctrl_datagram_is_21_bytes():
    assert len(p.pack(p.MsgType.AUDIO_TTS, p.audio_ctrl_payload(p.AudioCmd.MIC_ON))) == 21


def test_ctrl_roundtrip():
    chunk = p.unpack_audio_chunk(p.audio_ctrl_payload(p.AudioCmd.SELFTEST))
    assert chunk is not None
    assert chunk.fmt == p.AudioFmt.CTRL
    assert chunk.cmd == 3
    assert chunk.pcm is None
    assert chunk.samples == 0


def test_ctrl_payload_rejects_a_non_byte_cmd():
    with pytest.raises(ValueError, match="u8"):
        p.audio_ctrl_payload(256)


# ---- unpack_audio_chunk applies the drone's own acceptance rules ----------
def test_unpack_rejects_a_short_payload():
    assert p.unpack_audio_chunk(b"") is None
    assert p.unpack_audio_chunk(b"\x01\x00\x00") is None


def test_unpack_rejects_an_unknown_fmt():
    assert p.unpack_audio_chunk(p.pack_audio_header(3) + b"\x00\x00") is None
    assert p.unpack_audio_chunk(p.pack_audio_header(0) + b"\x00\x00") is None


def test_unpack_rejects_pcm_with_no_body_or_an_odd_body():
    assert p.unpack_audio_chunk(p.pack_audio_header(1)) is None
    assert p.unpack_audio_chunk(p.pack_audio_header(1) + b"\x00") is None


def test_unpack_rejects_pcm_over_the_cap():
    body = b"\x00" * (p.AUDIO_PCM_MAX_BYTES + 2)
    assert p.unpack_audio_chunk(p.pack_audio_header(1) + body) is None
    ok = b"\x00" * p.AUDIO_PCM_MAX_BYTES
    assert p.unpack_audio_chunk(p.pack_audio_header(1) + ok) is not None


def test_unpack_rejects_ctrl_with_no_command_byte():
    assert p.unpack_audio_chunk(p.pack_audio_header(2)) is None


def test_a_mic_sized_chunk_is_a_1044_byte_datagram():
    """The drone sends 512-sample blocks; PROTOCOL.md says that is 1044 bytes."""
    payload = p.audio_pcm_payload(b"\x00" * (p.AUDIO_MIC_BLOCK_SAMPLES * 2))
    assert len(p.pack(p.MsgType.AUDIO_MIC, payload)) == 1044


def test_start_and_end_flags_decode_independently():
    for flags, (start, end) in {
        0: (False, False),
        p.AU_F_START: (True, False),
        p.AU_F_END: (False, True),
        p.AU_F_START | p.AU_F_END: (True, True),
    }.items():
        chunk = p.unpack_audio_chunk(p.audio_pcm_payload(b"\x00\x00", flags=flags))
        assert chunk is not None
        assert (chunk.start, chunk.end) == (start, end)
