"""Receiving AUDIO_MIC (0x41): reassemble the drone's mic stream and write it to a WAV.

The mic is off on the drone until something sends `AUDIO_TTS fmt 2 cmd 1` (MIC_ON), and that
is a deliberate privacy position rather than an optimisation — it is a microphone on an
aircraft that follows people. So this class exists to *verify* the path end to end, not to
leave a recorder running: it keeps a bounded buffer (`CONFIG.mic_max_seconds`) and only
writes a file when asked.

Loss is visible, not concealed. `seq` gaps are counted and reported; nothing is reordered or
interpolated, because PROTOCOL.md is explicit that a gap in `seq` is an audible gap and
pretending otherwise would hide a link problem.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..config import CONFIG
from ..protocol import (AUDIO_RATE_HZ, AUDIO_SAMPLE_WIDTH, AudioChunk, AudioFmt,
                        unpack_audio_chunk)

log = logging.getLogger("kogane.audio.mic")


@dataclass
class MicStats:
    """What the inbound stream has done so far."""

    chunks: int = 0
    samples: int = 0
    malformed: int = 0
    gaps: int = 0
    lost_chunks: int = 0
    streams: int = 0
    ended: int = 0
    trimmed_samples: int = 0
    peak: int = 0
    last_seq: int | None = field(default=None)

    @property
    def duration_s(self) -> float:
        return self.samples / AUDIO_RATE_HZ

    def describe(self) -> str:
        return (f"{self.chunks} chunk(s), {self.samples} samples "
                f"({self.duration_s:.2f} s), peak {self.peak}, "
                f"{self.gaps} gap(s) / {self.lost_chunks} chunk(s) lost, "
                f"{self.malformed} malformed")


class MicRecorder:
    """Accumulates 0x41 PCM into a bounded buffer that can be written out as a WAV."""

    def __init__(self, max_seconds: float | None = None) -> None:
        self.max_samples = int(AUDIO_RATE_HZ * (CONFIG.mic_max_seconds
                                                if max_seconds is None else max_seconds))
        self._buf = bytearray()
        self.stats = MicStats()

    # ---- ingest --------------------------------------------------------------------
    def on_payload(self, payload: bytes) -> AudioChunk | None:
        """Decode and accept a raw 0x41 payload. Returns the chunk, or None if rejected."""
        chunk = unpack_audio_chunk(payload)
        if chunk is None or chunk.fmt != AudioFmt.PCM_S16LE:
            # A CTRL chunk on 0x41 is meaningless by definition (PROTOCOL.md §1) and is
            # counted with the malformed ones rather than acted on.
            self.stats.malformed += 1
            return None
        self.on_chunk(chunk)
        return chunk

    def on_chunk(self, chunk: AudioChunk) -> None:
        """Accept an already-decoded PCM chunk."""
        if chunk.pcm is None:
            self.stats.malformed += 1
            return

        st = self.stats
        if chunk.start:
            st.streams += 1
            st.last_seq = None
            log.info("AUDIO_MIC stream start (seq %d)", chunk.seq)
        elif st.last_seq is not None:
            expected = (st.last_seq + 1) & 0xFFFF
            if chunk.seq != expected:
                missing = (chunk.seq - expected) & 0xFFFF
                # A huge delta is a restart or a reorder, not 65000 lost chunks; do not
                # let it poison the loss count.
                if missing < 256:
                    st.gaps += 1
                    st.lost_chunks += missing
                    log.warning("AUDIO_MIC gap: expected seq %d, got %d (%d chunk(s) "
                                "lost = %.0f ms of audio)", expected, chunk.seq, missing,
                                missing * 32.0)
        st.last_seq = chunk.seq
        st.chunks += 1
        st.samples += chunk.samples
        st.peak = max(st.peak, _peak(chunk.pcm))
        if chunk.end:
            st.ended += 1
            log.info("AUDIO_MIC stream end at seq %d (%s)", chunk.seq, st.describe())

        self._buf += chunk.pcm
        limit = self.max_samples * AUDIO_SAMPLE_WIDTH
        if limit and len(self._buf) > limit:
            over = len(self._buf) - limit
            del self._buf[:over]
            st.trimmed_samples += over // AUDIO_SAMPLE_WIDTH

    # ---- output --------------------------------------------------------------------
    @property
    def pcm(self) -> bytes:
        """Everything buffered, as 16 kHz mono int16 little-endian bytes."""
        return bytes(self._buf)

    @property
    def buffered_s(self) -> float:
        return len(self._buf) / AUDIO_SAMPLE_WIDTH / AUDIO_RATE_HZ

    def write_wav(self, path: str | Path | None = None) -> Path | None:
        """Write the buffer to a 16 kHz mono WAV. None if there is nothing to write."""
        import numpy as np

        from .wav import write_wav as _write

        target = path if path is not None else CONFIG.mic_wav_path
        if not target:
            return None
        if not self._buf:
            log.warning("no AUDIO_MIC audio buffered — is the mic on? "
                        "send CTRL MIC_ON (kogane-audio --mic-on)")
            return None
        mono = np.frombuffer(bytes(self._buf), dtype="<i2")
        out = _write(target, mono)
        log.info("wrote %s: %.2f s of mic audio (%s)", out, self.buffered_s,
                 self.stats.describe())
        return out

    def reset(self) -> None:
        self._buf.clear()
        self.stats = MicStats()


def _peak(pcm: bytes) -> int:
    """Largest absolute sample in a PCM chunk, for a level readout."""
    import numpy as np

    if not pcm:
        return 0
    a = np.frombuffer(pcm, dtype="<i2").astype("int32")
    return int(np.abs(a).max())
