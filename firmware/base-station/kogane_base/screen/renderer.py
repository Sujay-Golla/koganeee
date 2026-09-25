"""Live panel readout: push the base station's own state to the drone's display.

Content: who is being tracked, where they are, whether that is a real measurement or the
Kalman filter extrapolating, and the drone's link quality. Frames are chunked into
SCREEN_FRAME datagrams sized for the ILI9341 panel by `screen.sender`.

Two things shape the design:

* **Off by default.** Any non-STATUS chunk takes the panel away from the drone's own status
  screen for 5 s, so a background loop running unasked would fight a manual
  `kogane-screen --image` for the display. `CONFIG.screen_enabled` gates the whole loop and
  defaults to false; with it off this task idles exactly like the old stub did.
* **State is pulled, not pushed.** The renderer holds a callable returning a
  `ReadoutState` snapshot rather than a reference to `BaseStation`, so it can be tested with
  a two-line lambda and does not care where the numbers came from.

Text mode is the default output: six `fmt=2` rows is six small datagrams, against 120 for a
full RGB565 repaint on a link that is also carrying setpoints at 30 Hz. `KGN_SCREEN_MODE=panel`
switches to a PIL-composed frame with a position plot when the picture matters more.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from ..config import CONFIG
from ..net.sink import FrameSink
from ..protocol import RGB565_AMBER, RGB565_BLACK, RGB565_CYAN, RGB565_WHITE
from .frames import ReadoutState
from .sender import ScreenSender

log = logging.getLogger("kogane.screen")

StateSource = Callable[[], ReadoutState]

# Row 0 is the title; give it the accent colour so the panel reads as "ours" at a glance.
_ROW_COLOURS = (RGB565_AMBER, RGB565_WHITE, RGB565_CYAN, RGB565_CYAN,
                RGB565_WHITE, RGB565_WHITE, RGB565_WHITE, RGB565_WHITE,
                RGB565_WHITE, RGB565_WHITE)


class ScreenRenderer:
    """Periodically renders `state()` to the drone panel.

    `sink` is optional so `BaseStation` can build the renderer before its UDP endpoint is
    bound, and so the constructor stays compatible with the stub it replaces
    (`ScreenRenderer()` still works and simply has nothing to send to).
    """

    def __init__(self, sink: FrameSink | None = None, state: StateSource | None = None,
                 *, enabled: bool | None = None, interval_s: float | None = None,
                 mode: str | None = None) -> None:
        self._running = False
        self.sink = sink
        self.state = state
        self.enabled = CONFIG.screen_enabled if enabled is None else bool(enabled)
        self.interval_s = (CONFIG.screen_interval_s if interval_s is None
                           else float(interval_s))
        self.mode = (CONFIG.screen_mode if mode is None else mode).strip().lower()
        self.sender = ScreenSender(sink) if sink is not None else None
        self.updates = 0
        self._last_lines: list[str] | None = None
        self._warned_panel = False

    def attach(self, sink: FrameSink) -> None:
        """Give the renderer somewhere to send. Safe to call before or after `run()`."""
        self.sink = sink
        self.sender = ScreenSender(sink)

    # ---- one update ---------------------------------------------------------------
    async def push_once(self) -> int:
        """Render and send one update. Returns the number of chunks sent."""
        if self.sender is None or self.state is None:
            return 0
        snapshot = self.state()
        if self.mode == "panel":
            return await self._push_panel(snapshot)
        return await self._push_text(snapshot)

    async def _push_text(self, snapshot: ReadoutState) -> int:
        from .frames import readout_lines

        lines = readout_lines(snapshot)
        # Only clear the panel when the shape of the readout changes. Redrawing a row
        # paints its own background, so a per-update full clear would just flicker.
        clear = self._last_lines is None or len(lines) != len(self._last_lines)
        self._last_lines = lines
        sent = 0
        for i, line in enumerate(lines):
            sent += await self.sender.asend_lines(
                [line], start_row=i, scale=CONFIG.screen_text_scale,
                fg=_ROW_COLOURS[i % len(_ROW_COLOURS)], bg=RGB565_BLACK,
                clear=clear and i == 0)
        self.updates += 1
        return sent

    async def _push_panel(self, snapshot: ReadoutState) -> int:
        from .frames import PillowMissing, compose_readout

        try:
            img = compose_readout(snapshot)
        except PillowMissing as e:
            if not self._warned_panel:
                self._warned_panel = True
                log.warning("screen mode 'panel' needs Pillow (%s) — falling back to "
                            "text rows", e)
            self.mode = "text"
            return await self._push_text(snapshot)
        sent = await self.sender.asend_frame(img)
        self.updates += 1
        return sent

    # ---- task --------------------------------------------------------------------
    async def run(self) -> None:
        self._running = True
        if not self.enabled:
            log.info("screen renderer idle (KGN_SCREEN unset) — the drone keeps its own "
                     "status screen; use `kogane-screen` to drive the panel by hand")
            while self._running:
                await asyncio.sleep(1.0)
            return
        if self.sink is None or self.state is None:
            log.warning("screen renderer enabled but has no %s — idling",
                        "sink" if self.sink is None else "state source")
            while self._running:
                await asyncio.sleep(1.0)
            return

        log.info("screen renderer started: mode=%s every %.1fs -> %s",
                 self.mode, self.interval_s, getattr(self.sink, "addr", "sink"))
        try:
            while self._running:
                t0 = time.monotonic()
                try:
                    await self.push_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # A panel update is never worth taking the control loop down for.
                    log.warning("screen update failed: %s", e)
                spent = time.monotonic() - t0
                await asyncio.sleep(max(0.05, self.interval_s - spent))
        finally:
            self._release_quietly()

    def _release_quietly(self) -> None:
        """Best effort hand-back on shutdown; the transport may already be closed."""
        if self.sender is None:
            return
        try:
            self.sender.release()
            log.info("panel released back to the drone's status screen")
        except Exception:  # pragma: no cover - depends on socket teardown order
            pass

    def stop(self) -> None:
        self._running = False
