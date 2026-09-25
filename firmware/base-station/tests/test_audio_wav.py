"""Tests for kogane_base.audio.wav: downmixing, resampling, chunking, WAV round trips.

All pure: temp files on disk, numpy in memory, no audio device and no drone.
"""
from __future__ import annotations

import struct
import wave

import numpy as np
import pytest

from kogane_base.audio import wav as w
from kogane_base.protocol import AUDIO_PCM_MAX_BYTES, AUDIO_RATE_HZ


def _write_raw(path, frames: bytes, *, channels: int, width: int, rate: int):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(width)
        f.setframerate(rate)
        f.writeframes(frames)
    return path


# ---- downmix -------------------------------------------------------------
def test_downmix_averages_stereo():
    stereo = np.array([[100, 300], [-100, 100], [0, 0]], dtype=np.int16)
    assert w.downmix(stereo).tolist() == [200, 0, 0]


def test_downmix_passes_mono_through_untouched():
    mono = np.array([1, -2, 3], dtype=np.int16)
    assert w.downmix(mono).tolist() == [1, -2, 3]
    assert w.downmix(mono.reshape(-1, 1)).tolist() == [1, -2, 3]


def test_downmix_cannot_overflow_on_a_loud_pair():
    """Summed in int32; naive int16 addition would wrap to a negative here."""
    loud = np.array([[32767, 32767], [-32768, -32768]], dtype=np.int16)
    out = w.downmix(loud)
    assert out.dtype == np.int16
    assert out.tolist() == [32767, -32768]


def test_downmix_handles_more_than_two_channels():
    quad = np.array([[400, 0, 0, 0]], dtype=np.int16)
    assert w.downmix(quad).tolist() == [100]


def test_downmix_rejects_a_3d_array():
    with pytest.raises(ValueError, match="expected"):
        w.downmix(np.zeros((2, 2, 2), dtype=np.int16))


# ---- resample ------------------------------------------------------------
def test_resample_is_a_no_op_at_the_same_rate():
    a = np.array([1, 2, 3], dtype=np.int16)
    assert w.resample_linear(a, 16000, 16000) is not None
    assert w.resample_linear(a, 16000, 16000).tolist() == [1, 2, 3]


def test_resample_halving_the_rate_halves_the_length():
    a = np.zeros(1000, dtype=np.int16)
    assert w.resample_linear(a, 32000, 16000).size == 500


def test_resample_44100_to_16000_length():
    a = np.zeros(44100, dtype=np.int16)          # one second
    out = w.resample_linear(a, 44100, AUDIO_RATE_HZ)
    assert out.size == AUDIO_RATE_HZ             # still one second
    assert out.dtype == np.int16


def test_resample_upsampling_interpolates_linearly():
    a = np.array([0, 100], dtype=np.int16)
    out = w.resample_linear(a, 1000, 2000, antialias=False)
    # positions 0, 0.5, 1, 1.5 -> 0, 50, 100, 100 (clamped at the right edge by np.interp)
    assert out.tolist() == [0, 50, 100, 100]


def test_resample_preserves_a_dc_level():
    a = np.full(4410, 1000, dtype=np.int16)
    out = w.resample_linear(a, 44100, 16000)
    assert out.size == 1600
    # The box pre-filter tapers the very edges; the middle must stay put.
    assert np.allclose(out[50:-50], 1000, atol=2)


def test_resample_keeps_a_sine_recognisable_and_in_range():
    t = np.arange(44100) / 44100.0
    a = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    out = w.resample_linear(a, 44100, AUDIO_RATE_HZ)
    assert out.size == AUDIO_RATE_HZ
    assert out.dtype == np.int16
    assert 15000 < np.abs(out).max() <= 32767
    # Energy should survive downsampling: 440 Hz is far below the 8 kHz Nyquist.
    assert np.sqrt((out.astype(float) ** 2).mean()) > 10000


def test_resample_antialias_reduces_out_of_band_energy():
    """A 15 kHz tone is above the 8 kHz Nyquist of 16 kHz; the filter must attenuate it."""
    t = np.arange(44100) / 44100.0
    a = (np.sin(2 * np.pi * 15000 * t) * 20000).astype(np.int16)
    filtered = w.resample_linear(a, 44100, AUDIO_RATE_HZ, antialias=True)
    raw = w.resample_linear(a, 44100, AUDIO_RATE_HZ, antialias=False)
    rms = lambda x: np.sqrt((x.astype(float) ** 2).mean())
    assert rms(filtered) < rms(raw) * 0.6


def test_resample_output_never_leaves_int16_range():
    a = np.full(1000, 32767, dtype=np.int16)
    out = w.resample_linear(a, 44100, 16000)
    assert out.min() >= -32768 and out.max() <= 32767


def test_resample_handles_an_empty_array():
    assert w.resample_linear(np.zeros(0, dtype=np.int16), 44100, 16000).size == 0


def test_resample_rejects_bad_rates_and_shapes():
    with pytest.raises(ValueError, match="rates must be positive"):
        w.resample_linear(np.zeros(4, dtype=np.int16), 0, 16000)
    with pytest.raises(ValueError, match="expected mono"):
        w.resample_linear(np.zeros((4, 2), dtype=np.int16), 44100, 16000)


# ---- load_wav ------------------------------------------------------------
def test_load_16bit_mono(tmp_path):
    pcm = struct.pack("<4h", 0, 1000, -1000, 32767)
    path = _write_raw(tmp_path / "a.wav", pcm, channels=1, width=2, rate=16000)
    samples, rate = w.load_wav(path)
    assert rate == 16000
    assert samples.shape == (4, 1)
    assert samples[:, 0].tolist() == [0, 1000, -1000, 32767]


def test_load_16bit_stereo_keeps_the_channels_separate(tmp_path):
    pcm = struct.pack("<4h", 100, 200, 300, 400)
    path = _write_raw(tmp_path / "s.wav", pcm, channels=2, width=2, rate=44100)
    samples, rate = w.load_wav(path)
    assert rate == 44100
    assert samples.shape == (2, 2)
    assert samples.tolist() == [[100, 200], [300, 400]]


def test_load_8bit_is_centred_and_scaled(tmp_path):
    """8-bit WAV is unsigned: 128 is silence, 255 is near full scale."""
    path = _write_raw(tmp_path / "e.wav", bytes([128, 255, 0]), channels=1, width=1,
                      rate=8000)
    samples, rate = w.load_wav(path)
    assert rate == 8000
    assert samples[:, 0].tolist() == [0, 32512, -32768]


def test_load_24bit(tmp_path):
    # 0x7FFFFF is full positive scale, 0x800000 full negative.
    raw = bytes([0x00, 0x00, 0x00]) + bytes([0xFF, 0xFF, 0x7F]) + bytes([0x00, 0x00, 0x80])
    path = _write_raw(tmp_path / "t.wav", raw, channels=1, width=3, rate=48000)
    samples, rate = w.load_wav(path)
    assert rate == 48000
    assert samples[:, 0].tolist() == [0, 32767, -32768]


def test_load_32bit_is_shifted_down_to_16(tmp_path):
    raw = struct.pack("<2i", 0x7FFF0000, -0x80000000)
    path = _write_raw(tmp_path / "f.wav", raw, channels=1, width=4, rate=16000)
    samples, _ = w.load_wav(path)
    assert samples[:, 0].tolist() == [0x7FFF, -32768]


def test_wav_probe_reports_the_header(tmp_path):
    path = _write_raw(tmp_path / "p.wav", b"\x00" * 800, channels=2, width=2, rate=8000)
    info = w.wav_probe(path)
    assert (info.rate, info.channels, info.sample_width, info.frames) == (8000, 2, 2, 200)
    assert info.duration_s == pytest.approx(0.025)
    assert "8000 Hz" in info.describe()


# ---- to_kgn_pcm ----------------------------------------------------------
def test_to_kgn_pcm_passes_through_16k_mono(tmp_path):
    pcm = struct.pack("<3h", 1, 2, 3)
    path = _write_raw(tmp_path / "ok.wav", pcm, channels=1, width=2, rate=16000)
    out = w.to_kgn_pcm(path)
    assert out.dtype == np.int16
    assert out.tolist() == [1, 2, 3]


def test_to_kgn_pcm_downmixes_and_resamples_together(tmp_path):
    """Half a second of 44.1 kHz stereo must come out as 8000 mono samples."""
    n = 22050
    stereo = np.zeros((n, 2), dtype=np.int16)
    stereo[:, 0] = 1000
    stereo[:, 1] = 3000
    path = _write_raw(tmp_path / "x.wav", stereo.tobytes(), channels=2, width=2,
                      rate=44100)
    out = w.to_kgn_pcm(path)
    assert out.ndim == 1
    assert out.dtype == np.int16
    assert out.size == 8000
    assert np.allclose(out[100:-100], 2000, atol=2)      # (1000 + 3000) / 2


def test_to_kgn_pcm_accepts_an_array_plus_a_rate():
    out = w.to_kgn_pcm(np.zeros(8000, dtype=np.int16), rate=8000)
    assert out.size == 16000


def test_to_kgn_pcm_needs_a_rate_for_raw_samples():
    with pytest.raises(ValueError, match="rate is required"):
        w.to_kgn_pcm(np.zeros(10, dtype=np.int16))


# ---- chunking ------------------------------------------------------------
def test_chunk_pcm_at_the_1440_byte_cap():
    data = b"\x00" * 5000
    chunks = w.chunk_pcm(data, AUDIO_PCM_MAX_BYTES)
    assert [len(c) for c in chunks] == [1440, 1440, 1440, 680]
    assert sum(len(c) for c in chunks) == 5000
    assert b"".join(chunks) == data


def test_chunk_pcm_exactly_divides():
    chunks = w.chunk_pcm(b"\x00" * 2880, 1440)
    assert [len(c) for c in chunks] == [1440, 1440]


def test_chunk_pcm_every_chunk_is_within_the_cap_and_whole_samples():
    chunks = w.chunk_pcm(b"\x01" * 12345, 640)
    assert all(len(c) <= 640 and len(c) % 2 == 0 for c in chunks[:-1])
    assert len(chunks[-1]) % 2 == 0
    assert all(len(c) <= AUDIO_PCM_MAX_BYTES for c in chunks)


def test_chunk_pcm_rounds_an_odd_max_down_to_a_whole_sample():
    chunks = w.chunk_pcm(b"\x00" * 100, 11)
    assert all(len(c) % 2 == 0 for c in chunks)
    assert max(len(c) for c in chunks) == 10


def test_chunk_pcm_drops_a_trailing_half_sample():
    chunks = w.chunk_pcm(b"\x00" * 101, 1440)
    assert sum(len(c) for c in chunks) == 100


def test_chunk_pcm_rejects_a_max_over_the_wire_cap():
    with pytest.raises(ValueError, match="exceeds the 1440-byte cap"):
        w.chunk_pcm(b"\x00" * 10, AUDIO_PCM_MAX_BYTES + 2)


def test_chunk_pcm_rejects_a_max_below_one_sample():
    with pytest.raises(ValueError, match="at least 2"):
        w.chunk_pcm(b"\x00" * 10, 1)


def test_chunk_pcm_of_nothing_is_nothing():
    assert w.chunk_pcm(b"") == []


def test_samples_for_ms():
    assert w.samples_for_ms(20) == 320          # 20 ms at 16 kHz
    assert w.samples_for_ms(45) == 720          # the cap
    assert w.samples_for_ms(0.001) == 1         # never zero


# ---- generators ----------------------------------------------------------
def test_tone_length_rate_and_range():
    t = w.tone(660, 0.5)
    assert t.dtype == np.int16
    assert t.size == 8000
    assert t.min() >= -32768 and t.max() <= 32767


def test_tone_amplitude_is_respected():
    assert np.abs(w.tone(440, 0.2, amplitude=0.5)).max() <= int(0.5 * 32767) + 1
    assert np.abs(w.tone(440, 0.2, amplitude=1.0)).max() > 32000


def test_tone_fades_in_and_out_so_it_does_not_click():
    t = w.tone(440, 0.2, fade_ms=15.0)
    assert abs(int(t[0])) < 500
    assert abs(int(t[-1])) < 500


def test_tone_amplitude_is_clamped_not_wrapped():
    assert np.abs(w.tone(440, 0.05, amplitude=5.0)).max() <= 32767


def test_tone_rejects_a_zero_length():
    with pytest.raises(ValueError, match="seconds must be positive"):
        w.tone(440, 0.0)


def test_chirp_is_the_three_notes_back_to_back():
    c = w.chirp(seconds_each=0.1)
    assert c.size == 3 * 1600
    assert c.dtype == np.int16


# ---- write_wav -----------------------------------------------------------
def test_write_wav_roundtrips_through_load(tmp_path):
    original = w.tone(440, 0.25)
    path = w.write_wav(tmp_path / "out.wav", original)
    info = w.wav_probe(path)
    assert (info.rate, info.channels, info.sample_width) == (AUDIO_RATE_HZ, 1, 2)
    back, rate = w.load_wav(path)
    assert rate == AUDIO_RATE_HZ
    assert back[:, 0].tolist() == original.tolist()


def test_write_wav_creates_parent_directories(tmp_path):
    path = w.write_wav(tmp_path / "deep" / "er" / "x.wav", np.zeros(10, dtype=np.int16))
    assert path.exists()


def test_pcm_to_bytes_is_little_endian():
    assert w.pcm_to_bytes(np.array([1, -1], dtype=np.int16)) == b"\x01\x00\xff\xff"
