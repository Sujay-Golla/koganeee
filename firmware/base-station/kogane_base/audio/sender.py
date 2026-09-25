"""Streaming AUDIO_TTS (0x40) to the drone speaker, paced to real time.

The one rule that shapes this whole file: **the drone's playback queue holds 12 chunks and
drops the OLDEST on overflow.** A sender that blasts a whole file as fast as the socket will
take it does not get a slightly delayed playback — it gets the *beginning* of the utterance
thrown away, which is the worst possible failure mode because the audio that arrives sounds
fine and the missing part is the part that said what it was about.

So `stream_pcm` sleeps. It keeps a fixed lead (`CONFIG.audio_lead_ms`, default 120 ms, i.e.
six 20 ms chunks against a queue of twelve) so host scheduling jitter cannot starve the
speaker, and never more than that.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Iterable

import numpy as np

from ..config import CONFIG
from ..net.sink import FrameSink
from ..protocol import (AU_F_END, AU_F_START, AUDIO_PCM_MAX_BYTES, AUDIO_RATE_HZ,
                        AUDIO_SAMPLE_WIDTH, AUDIO_TTS_QUEUE_DEPTH, AudioCmd, MsgType,
                        audio_ctrl_payload, audio_pcm_payload)
from .wav import chunk_pcm, pcm_to_bytes, samples_for_ms, to_kgn_pcm, tone

log = logging.getLogger("kogane.audio")

ProgressFn = Callable[[int, int], None]  # (chunk_index, total_chunks)


def pcm_payloads(pcm: bytes, *, chunk_bytes: int = AUDIO_PCM_MAX_BYTES,
                 start_seq: int = 0, start: bool = True,
                 end: bool = True) -> list[bytes]:
    """Complete `fmt=1` payloads for one utterance, START on the first, END on the last.

    Pure. `pcm` is 16 kHz mono signed-16 little-endian. A single-chunk utterance carries
    both flags, which is correct and is what a short "yes" looks like on the wire.
    """
    chunks = chunk_pcm(pcm, chunk_bytes)
    out: list[bytes] = []
    last = len(chunks) - 1
    for i, chunk in enumerate(chunks):
        flags = 0
        if start and i == 0:
            flags |= AU_F_START
        if end and i == last:
            flags |= AU_F_END
        out.append(audio_pcm_payload(chunk, seq=(start_seq + i) & 0xFFFF, flags=flags))
    return out


class AudioSender:
    """CTRL commands and paced PCM streaming onto a `FrameSink`.

    Synchronous by default for the CLI; `astream_pcm` is the event-loop twin so the base
    station can speak without stalling the 30 Hz setpoint loop.
    """

    def __init__(self, sink: FrameSink, *, chunk_ms: float | None = None,
                 lead_ms: float | None = None) -> None:
        self.sink = sink
        self.chunk_ms = CONFIG.audio_chunk_ms if chunk_ms is None else float(chunk_ms)
        self.lead_s = (CONFIG.audio_lead_ms if lead_ms is None else float(lead_ms)) / 1000.0
        self._seq = 0
        self.chunks_sent = 0

        if self.chunk_bytes > AUDIO_PCM_MAX_BYTES:
            raise ValueError(
                f"chunk_ms={self.chunk_ms:g} is {self.chunk_bytes} bytes; the drone drops "
                f"anything over {AUDIO_PCM_MAX_BYTES} "
                f"({1000.0 * AUDIO_PCM_MAX_BYTES / 2 / AUDIO_RATE_HZ:.0f} ms)")
        lead_chunks = self.lead_s / max(self.chunk_s, 1e-6)
        if lead_chunks > AUDIO_TTS_QUEUE_DEPTH:
            log.warning("audio lead is %.1f chunks but the drone queues %d and drops the "
                        "oldest — the start of each utterance will be cut",
                        lead_chunks, AUDIO_TTS_QUEUE_DEPTH)

    # ---- geometry ------------------------------------------------------------------
    @property
    def chunk_samples(self) -> int:
        return samples_for_ms(self.chunk_ms)

    @property
    def chunk_bytes(self) -> int:
        return self.chunk_samples * AUDIO_SAMPLE_WIDTH

    @property
    def chunk_s(self) -> float:
        return self.chunk_samples / AUDIO_RATE_HZ

    def next_seq(self, n: int = 1) -> int:
        """Reserve `n` stream sequence numbers and return the first."""
        first = self._seq
        self._seq = (self._seq + n) & 0xFFFF
        return first

    # ---- control -------------------------------------------------------------------
    def send_ctrl(self, cmd: AudioCmd | int) -> None:
        """One `fmt=2` command. Base -> drone only, by definition.

        `seq` is left at 0: it means "chunk index within this audio stream" and a control
        byte is not part of one, so advancing the PCM counter here would only put a
        phantom gap in the next utterance.
        """
        self.sink.send(MsgType.AUDIO_TTS, audio_ctrl_payload(cmd, seq=0))
        known = {int(c) for c in AudioCmd}
        log.info("AUDIO_TTS ctrl %s", AudioCmd(cmd).name if int(cmd) in known else cmd)

    def mic_on(self) -> None:
        """Ask the drone to start streaming AUDIO_MIC. It boots with this off."""
        self.send_ctrl(AudioCmd.MIC_ON)

    def mic_off(self) -> None:
        self.send_ctrl(AudioCmd.MIC_OFF)

    def selftest(self) -> None:
        """Fire the drone's own speaker self-test tone. Proves the amp without the link."""
        self.send_ctrl(AudioCmd.SELFTEST)

    def flush(self) -> None:
        """Drop everything queued on the drone and go silent now."""
        self.send_ctrl(AudioCmd.FLUSH)

    # ---- PCM -----------------------------------------------------------------------
    def build_payloads(self, pcm: bytes, *, start: bool = True,
                       end: bool = True) -> list[bytes]:
        """Chunk `pcm` into `fmt=1` payloads with this sender's stream sequence numbers.

        `seq` restarts at 0 whenever START is set, because PROTOCOL.md defines it as the
        index *within this audio stream* — an utterance. Continuation calls
        (`start=False`) carry on from where the last one stopped.
        """
        if start:
            self._seq = 0
        n_chunks = -(-len(pcm) // max(1, self.chunk_bytes))
        return pcm_payloads(pcm, chunk_bytes=self.chunk_bytes,
                            start_seq=self.next_seq(n_chunks), start=start, end=end)

    def stream_pcm(self, pcm, *, realtime: bool = True, start: bool = True,
                   end: bool = True, on_progress: ProgressFn | None = None) -> int:
        """Stream PCM to the drone speaker. Returns the number of chunks sent.

        `pcm` is bytes of 16 kHz mono int16, or a numpy int16 array. `realtime=False` sends
        as fast as the socket takes it, which is only useful for loopback tests — against a
        real drone it loses the start of the audio.
        """
        data = pcm if isinstance(pcm, (bytes, bytearray, memoryview)) else pcm_to_bytes(pcm)
        payloads = self.build_payloads(bytes(data), start=start, end=end)
        return self._drive(payloads, realtime=realtime, on_progress=on_progress,
                           sleep=time.sleep)

    async def astream_pcm(self, pcm, *, realtime: bool = True, start: bool = True,
                          end: bool = True,
                          on_progress: ProgressFn | None = None) -> int:
        data = pcm if isinstance(pcm, (bytes, bytearray, memoryview)) else pcm_to_bytes(pcm)
        payloads = self.build_payloads(bytes(data), start=start, end=end)
        total = len(payloads)
        t0 = time.monotonic()
        for i, payload in enumerate(payloads):
            self.sink.send(MsgType.AUDIO_TTS, payload)
            self.chunks_sent += 1
            if on_progress:
                on_progress(i, total)
            if realtime:
                target = t0 + (i + 1) * self.chunk_s - self.lead_s
                gap = target - time.monotonic()
                if gap > 0:
                    await asyncio.sleep(gap)
        return total

    def _drive(self, payloads: Iterable[bytes], *, realtime: bool,
               on_progress: ProgressFn | None, sleep) -> int:
        payloads = list(payloads)
        total = len(payloads)
        t0 = time.monotonic()
        for i, payload in enumerate(payloads):
            self.sink.send(MsgType.AUDIO_TTS, payload)
            self.chunks_sent += 1
            if on_progress:
                on_progress(i, total)
            if realtime:
                # Absolute schedule, not a fixed per-chunk sleep: a slow send does not
                # accumulate drift, it just eats into the lead.
                target = t0 + (i + 1) * self.chunk_s - self.lead_s
                gap = target - time.monotonic()
                if gap > 0:
                    sleep(gap)
        return total

    # ---- convenience ---------------------------------------------------------------
    def send_wav(self, path, *, realtime: bool = True,
                 on_progress: ProgressFn | None = None) -> int:
        """Load a WAV of any rate/channel count, convert, and stream it."""
        pcm = to_kgn_pcm(path)
        log.info("streaming %s: %d samples, %.2f s, %d chunk(s) of %.0f ms",
                 path, pcm.size, pcm.size / AUDIO_RATE_HZ,
                 max(1, -(-pcm.size * 2 // self.chunk_bytes)), self.chunk_ms)
        return self.stream_pcm(pcm, realtime=realtime, on_progress=on_progress)

    def send_tone(self, freq_hz: float = 660.0, seconds: float = 1.0,
                  amplitude: float = 0.35, *, realtime: bool = True) -> int:
        """Generate and stream a test tone. No audio file needed to check the speaker."""
        return self.stream_pcm(tone(freq_hz, seconds, amplitude=amplitude),
                               realtime=realtime)

    def send_silence(self, seconds: float = 0.2, *, realtime: bool = True) -> int:
        """Pad with silence. Handy as a tail so the last real chunk is not clipped."""
        n = max(1, int(round(AUDIO_RATE_HZ * seconds)))
        return self.stream_pcm(np.zeros(n, dtype=np.int16), realtime=realtime)
