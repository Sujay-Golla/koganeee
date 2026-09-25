"""PCM handling for the drone audio link. Pure: stdlib `wave` + numpy, no sockets.

`fmt = 1` on the wire is a *fixed* format — 16000 Hz, signed 16-bit little-endian, mono —
because the drone's mic and speaker share one I2S bus in full duplex and cannot clock the
two directions at different rates (PROTOCOL.md §1). Nothing is negotiated, so anything
handed to the sender has to be converted to exactly that here.

Resampling is linear interpolation with a box pre-filter when decimating. That is not a
good resampler, and for speech on a 4 ohm drone speaker it does not need to be: the
alternative is a scipy dependency for something nobody will hear through rotor noise. The
pre-filter is there because plain linear interpolation from 44.1 kHz to 16 kHz aliases
audibly, and a moving average is three lines.
"""
from __future__ import annotations

import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..protocol import AUDIO_PCM_MAX_BYTES, AUDIO_RATE_HZ, AUDIO_SAMPLE_WIDTH

log = logging.getLogger("kogane.audio.wav")


@dataclass
class WavInfo:
    """What a WAV file says about itself, before any conversion."""

    path: str
    rate: int
    channels: int
    sample_width: int
    frames: int

    @property
    def duration_s(self) -> float:
        return self.frames / self.rate if self.rate else 0.0

    def describe(self) -> str:
        return (f"{Path(self.path).name}: {self.rate} Hz, {self.channels} ch, "
                f"{self.sample_width * 8}-bit, {self.frames} frames "
                f"({self.duration_s:.2f} s)")


def wav_probe(path) -> WavInfo:
    """Read just the header. Used by the CLI so it can say what it is about to convert."""
    with wave.open(str(path), "rb") as w:
        return WavInfo(str(path), w.getframerate(), w.getnchannels(),
                       w.getsampwidth(), w.getnframes())


def load_wav(path) -> tuple[np.ndarray, int]:
    """Read a WAV into an `(n, channels)` int16 array plus its sample rate.

    Handles the integer PCM widths `wave` can hand back: 8-bit unsigned, 16-bit, 24-bit and
    32-bit signed, all little-endian. Anything compressed (or IEEE float, which `wave`
    reports as a non-NONE comptype or an unexpected width) raises with a clear message
    rather than producing noise.
    """
    with wave.open(str(path), "rb") as w:
        if w.getcomptype() != "NONE":
            raise ValueError(f"{path}: compressed WAV ({w.getcompname()}); "
                             "only uncompressed integer PCM is supported")
        ch = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if ch < 1:
        raise ValueError(f"{path}: {ch} channels")

    if width == 1:
        # 8-bit WAV is unsigned by definition; centre it before scaling.
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128) << 8
    elif width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.int16)
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8)
        usable = (len(b) // 3) * 3
        trip = b[:usable].reshape(-1, 3).astype(np.int32)
        v = trip[:, 0] | (trip[:, 1] << 8) | (trip[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)       # sign extend
        a = (v >> 8).astype(np.int16)
    elif width == 4:
        a = (np.frombuffer(raw, dtype="<i4") >> 16).astype(np.int16)
    else:
        raise ValueError(f"{path}: {width * 8}-bit samples are not supported "
                         "(expected 8, 16, 24 or 32-bit integer PCM)")

    usable = (len(a) // ch) * ch
    if usable != len(a):
        log.warning("%s: %d trailing sample(s) are not a whole frame; dropped",
                    path, len(a) - usable)
    return a[:usable].reshape(-1, ch), rate


def downmix(samples: np.ndarray) -> np.ndarray:
    """`(n, channels)` -> `(n,)` int16 by averaging. Already-mono input passes through.

    Averaged in int32 so a loud stereo pair cannot wrap around mid-sum, then clipped once
    at the end.
    """
    a = np.asarray(samples)
    if a.ndim == 1:
        return a.astype(np.int16, copy=False)
    if a.ndim != 2:
        raise ValueError(f"expected (n,) or (n, channels); got shape {a.shape}")
    if a.shape[1] == 1:
        return a[:, 0].astype(np.int16, copy=False)
    mixed = a.astype(np.int32).sum(axis=1) // a.shape[1]
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def resample_linear(mono: np.ndarray, src_rate: int, dst_rate: int,
                    antialias: bool = True) -> np.ndarray:
    """Resample mono int16 from `src_rate` to `dst_rate` by linear interpolation.

    With `antialias` and a decimation ratio of 2 or more, a box filter of the decimation
    width runs first. Crude, but it is the difference between intelligible speech and a
    metallic buzz when going 44100 -> 16000.
    """
    a = np.asarray(mono)
    if a.ndim != 1:
        raise ValueError(f"expected mono; got shape {a.shape}")
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError(f"rates must be positive; got {src_rate} -> {dst_rate}")
    if src_rate == dst_rate:
        return a.astype(np.int16, copy=False)
    if a.size == 0:
        return a.astype(np.int16, copy=False)

    x = a.astype(np.float64)
    if antialias and src_rate > dst_rate:
        width = int(src_rate // dst_rate)
        if width >= 2:
            kernel = np.ones(width, dtype=np.float64) / width
            x = np.convolve(x, kernel, mode="same")

    n_out = max(1, int(round(a.size * dst_rate / src_rate)))
    pos = np.arange(n_out, dtype=np.float64) * (src_rate / dst_rate)
    out = np.interp(pos, np.arange(a.size, dtype=np.float64), x)
    return np.clip(np.rint(out), -32768, 32767).astype(np.int16)


def to_kgn_pcm(source, rate: int | None = None) -> np.ndarray:
    """Anything -> mono int16 at `AUDIO_RATE_HZ`, i.e. exactly what `fmt = 1` means.

    `source` is a path to a WAV file, or an array plus its `rate`. Multi-channel input is
    downmixed and off-rate input is resampled; 16 kHz mono int16 passes through untouched.
    """
    if isinstance(source, (str, Path)):
        samples, src_rate = load_wav(source)
    else:
        if rate is None:
            raise ValueError("rate is required when passing samples instead of a path")
        samples, src_rate = np.asarray(source), int(rate)

    mono = downmix(samples)
    if src_rate != AUDIO_RATE_HZ:
        log.info("resampling %d Hz -> %d Hz (%d samples in)", src_rate, AUDIO_RATE_HZ,
                 mono.size)
        mono = resample_linear(mono, src_rate, AUDIO_RATE_HZ)
    return mono.astype(np.int16, copy=False)


def pcm_to_bytes(mono: np.ndarray) -> bytes:
    """Mono int16 -> little-endian bytes, which is the `fmt = 1` body."""
    return np.asarray(mono).astype("<i2", copy=False).tobytes()


def chunk_pcm(data: bytes, max_bytes: int = AUDIO_PCM_MAX_BYTES) -> list[bytes]:
    """Split a PCM byte string into chunks of at most `max_bytes`, on sample boundaries.

    `max_bytes` is rounded down to a whole sample because the drone masks the body length
    to a multiple of two and would silently lose the odd byte.
    """
    if max_bytes < AUDIO_SAMPLE_WIDTH:
        raise ValueError(f"max_bytes must be at least {AUDIO_SAMPLE_WIDTH}")
    if max_bytes > AUDIO_PCM_MAX_BYTES:
        raise ValueError(f"max_bytes {max_bytes} exceeds the {AUDIO_PCM_MAX_BYTES}-byte "
                         "cap the drone enforces")
    step = max_bytes - (max_bytes % AUDIO_SAMPLE_WIDTH)
    usable = len(data) - (len(data) % AUDIO_SAMPLE_WIDTH)
    if usable != len(data):
        log.warning("dropping %d trailing byte(s): PCM must be whole int16 samples",
                    len(data) - usable)
    body = bytes(data[:usable])
    return [body[i:i + step] for i in range(0, usable, step)]


def samples_for_ms(ms: float, rate: int = AUDIO_RATE_HZ) -> int:
    """Whole samples in `ms` milliseconds, at least one."""
    return max(1, int(round(rate * ms / 1000.0)))


def tone(freq_hz: float = 660.0, seconds: float = 1.0, *, rate: int = AUDIO_RATE_HZ,
         amplitude: float = 0.35, fade_ms: float = 15.0) -> np.ndarray:
    """A mono int16 sine, with a short fade in/out so it does not click.

    Default amplitude is well under full scale: the drone's amp is driving a 3 W speaker a
    metre from someone's face, and a full-scale test tone is unpleasant.
    """
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    amplitude = min(max(amplitude, 0.0), 1.0)
    n = max(1, int(round(rate * seconds)))
    t = np.arange(n, dtype=np.float64) / rate
    x = np.sin(2.0 * np.pi * freq_hz * t) * amplitude

    fade = min(int(round(rate * fade_ms / 1000.0)), n // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade)
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]
    return np.clip(np.rint(x * 32767.0), -32768, 32767).astype(np.int16)


def chirp(freqs=(660.0, 880.0, 1320.0), seconds_each: float = 0.25,
          *, rate: int = AUDIO_RATE_HZ, amplitude: float = 0.35) -> np.ndarray:
    """The same three-note sequence the drone's own self-test plays, generated host-side.

    Useful for telling the two paths apart: if `--selftest` sounds fine but this does not,
    the speaker is good and the problem is on the network/queue side.
    """
    return np.concatenate([tone(f, seconds_each, rate=rate, amplitude=amplitude)
                           for f in freqs])


def write_wav(path, mono: np.ndarray, rate: int = AUDIO_RATE_HZ) -> Path:
    """Write mono int16 to an uncompressed 16-bit WAV. Creates parent directories."""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(mono).astype("<i2", copy=False)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(AUDIO_SAMPLE_WIDTH)
        w.setframerate(int(rate))
        w.writeframes(data.tobytes())
    return p
