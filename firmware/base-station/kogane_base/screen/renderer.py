"""Screen renderer (stub): build UI frames and stream them to the drone display.

Content: conversation transcript, status (mode/battery/link), widgets. Frames are chunked
into SCREEN_FRAME datagrams sized for the ILI9341 panel driven by the ESP32.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("kogane.screen")


class ScreenRenderer:
    def __init__(self) -> None:
        self._running = False

    async def run(self) -> None:
        self._running = True
        log.info("screen renderer started (stub)")
        # TODO(kogane): render frames (PIL/skia), diff, chunk into SCREEN_FRAME, send to drone.
        while self._running:
            await asyncio.sleep(1.0)

    def stop(self) -> None:
        self._running = False
