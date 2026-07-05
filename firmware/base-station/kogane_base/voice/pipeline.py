"""Voice pipeline (stub): wakeword -> VAD -> STT -> intent -> LLM/local -> TTS.

Local commands (Come here, Follow me, Stop, Dock, ...) resolve to MODE_CMD/SETPOINT and
must work offline. Complex queries go to the cloud stack. See planning.md §4.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("kogane.voice")

LOCAL_COMMANDS = {
    "come here": "follow",
    "follow me": "follow",
    "stop": "hold",
    "stay": "hold",
    "dock": "dock",
    "land": "land",
}


class VoicePipeline:
    """Owns the audio-in -> action-out flow. Stubbed; wire real models per pyproject extras."""

    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        log.info("voice pipeline started (stub)")
        # TODO(kogane): openWakeWord on mic (from drone AUDIO_MIC), Silero VAD, Deepgram STT,
        #               intent match against LOCAL_COMMANDS, else Claude; ElevenLabs TTS ->
        #               AUDIO_TTS to the drone speaker.
        while self._running:
            await asyncio.sleep(1.0)

    def stop(self) -> None:
        self._running = False
