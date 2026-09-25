"""Turning frames into SCREEN_FRAME (0x30) datagrams and pacing them onto the wire.

Split in two on purpose:

* the `*_payloads` functions are pure — frame in, list of complete 0x30 payloads out. They
  are where the chunking, the flags and the geometry live, and they are what the tests
  assert on, with no socket anywhere near them.
* `ScreenSender` is the thin driver that hands those payloads to a `FrameSink` with a delay
  between them.

Why the pacing matters: the drone renders each chunk as it arrives, from a queue four deep
served by a priority-3 task that does a synchronous SPI blit per chunk. A 320x240 repaint is
120 datagrams; sent back to back they arrive far faster than the panel can absorb and the
overflow is dropped, which shows up as missing horizontal strips. So strips go out with a
gap, configurable via `CONFIG.screen_strip_delay_ms`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable, Sequence

from ..config import CONFIG
from ..net.sink import FrameSink
from ..protocol import (MsgType, RGB565_BLACK, RGB565_WHITE, SCREEN_H, SCREEN_TEXT_MAX,
                        SCREEN_TEXT_ROWS, SCREEN_TEXT_SCALE_MAX, SCREEN_TILE_MAX_PIXELS,
                        SCREEN_W, SF_F_FIRST, SF_F_LAST, SCREEN_BAND_PIXELS,
                        screen_status_payload, screen_text_payload, screen_text_sanitise,
                        screen_tile_payload)

log = logging.getLogger("kogane.screen")


def max_strip_rows(w: int = SCREEN_W) -> int:
    """Tallest full-width strip that fits one datagram *and* the drone's band buffer.

    For w=320 this is 2 (1280 bytes); 3 rows would be 1920 and every chunk would be
    dropped for exceeding the 1440-byte tile budget.
    """
    if w <= 0:
        raise ValueError("w must be positive")
    return max(1, min(SCREEN_TILE_MAX_PIXELS // w, SCREEN_BAND_PIXELS // w))


def prepare_text(text: str, warn: bool = True) -> str:
    """Sanitise and truncate one line to what the drone will actually render.

    Two lossy steps, both of which the drone would do silently, so we do them here and say
    what happened: characters outside 0x20..0x7E become '?', and anything past 53 chars is
    cut. Truncation is logged at WARNING because a line that is quietly half-shown is a
    confusing thing to debug from across a room.
    """
    clean = screen_text_sanitise(text)
    if warn and clean != text:
        log.warning("screen text: %d character(s) are not in the drone's 5x7 font and "
                    "will show as '?': %r", sum(a != b for a, b in zip(clean, text)), text)
    if len(clean) > SCREEN_TEXT_MAX:
        if warn:
            log.warning("screen text truncated to %d chars (dropped %r)",
                        SCREEN_TEXT_MAX, clean[SCREEN_TEXT_MAX:])
        clean = clean[:SCREEN_TEXT_MAX]
    return clean


def text_payloads(lines: Sequence[str] | str, *, start_row: int = 0, scale: int = 2,
                  fg: int = RGB565_WHITE, bg: int = RGB565_BLACK, frame_id: int = 0,
                  clear: bool = False, warn: bool = True) -> list[bytes]:
    """One `fmt=2` payload per line, rows counting up from `start_row`.

    `clear=True` sets FIRST on the first chunk, which makes the drone blank the whole panel
    before drawing — use it when replacing a previous frame, skip it when updating a couple
    of rows in place. Lines that would fall past row 9 are dropped with a warning rather
    than wrapping, matching the drone's own refusal to render `row >= 10`.
    """
    if isinstance(lines, str):
        lines = [lines]
    if scale > SCREEN_TEXT_SCALE_MAX and warn:
        log.warning("screen text scale %d will be clamped to %d on the drone "
                    "(a 24 px row holds 3x an 8 px cell)", scale, SCREEN_TEXT_SCALE_MAX)

    usable = [ln for i, ln in enumerate(lines) if start_row + i < SCREEN_TEXT_ROWS]
    if warn and len(usable) != len(lines):
        log.warning("%d line(s) past row %d dropped; the panel has %d text rows",
                    len(lines) - len(usable), SCREEN_TEXT_ROWS - 1, SCREEN_TEXT_ROWS)

    out: list[bytes] = []
    total = len(usable)
    for i, line in enumerate(usable):
        flags = 0
        if clear and i == 0:
            flags |= SF_F_FIRST
        if i == total - 1:
            flags |= SF_F_LAST
        out.append(screen_text_payload(
            prepare_text(line, warn=warn), row=start_row + i, scale=scale, fg=fg, bg=bg,
            frame_id=frame_id, chunk_idx=i, chunk_cnt=total, flags=flags))
    return out


def image_payloads(pixels565: bytes, *, w: int = SCREEN_W, h: int = SCREEN_H,
                   x0: int = 0, y0: int = 0, frame_id: int = 0,
                   strip_rows: int | None = None, clear: bool = True) -> list[bytes]:
    """Chop an RGB565 image into full-width `fmt=1` strips, in top-to-bottom order.

    `pixels565` is `w*h` little-endian RGB565 samples row-major (what
    `frames.image_to_rgb565` returns). Returns complete 0x30 payloads with FIRST on the
    first and LAST on the last.

    `chunk_idx` and `chunk_cnt` are u8. A frame needing more than 255 strips cannot express
    a count, so `chunk_cnt` goes to 0 ("streaming") and `chunk_idx` wraps — both fields are
    informational per PROTOCOL.md, and the drone renders each chunk regardless.
    """
    if w <= 0 or h <= 0:
        raise ValueError(f"image must be non-empty; got {w}x{h}")
    want = w * h * 2
    if len(pixels565) < want:
        raise ValueError(f"{w}x{h} needs {want} RGB565 bytes; got {len(pixels565)}")

    cap = max_strip_rows(w)
    rows = cap if strip_rows is None else int(strip_rows)
    if rows < 1:
        raise ValueError(f"strip_rows must be >= 1; got {strip_rows}")
    if rows > cap:
        log.warning("strip_rows=%d is %d bytes per chunk, over the %d-byte tile budget; "
                    "using %d", rows, w * rows * 2, SCREEN_TILE_MAX_PIXELS * 2, cap)
        rows = cap

    starts = list(range(0, h, rows))
    total = len(starts)
    wire_cnt = total if total <= 0xFF else 0

    out: list[bytes] = []
    stride = w * 2
    for i, top in enumerate(starts):
        sh = min(rows, h - top)
        flags = 0
        if clear and i == 0:
            flags |= SF_F_FIRST
        if i == total - 1:
            flags |= SF_F_LAST
        chunk = pixels565[top * stride:(top + sh) * stride]
        out.append(screen_tile_payload(x0, y0 + top, w, sh, chunk, frame_id=frame_id,
                                       chunk_idx=i & 0xFF, chunk_cnt=wire_cnt,
                                       flags=flags))
    return out


class ScreenSender:
    """Paces SCREEN_FRAME payloads onto a `FrameSink`.

    Synchronous by default (`time.sleep`) because that is what the CLI wants; every send
    method has an `a`-prefixed coroutine twin for use inside the base station's event loop,
    where blocking for half a second would stall the setpoint loop.
    """

    def __init__(self, sink: FrameSink, *, strip_delay_s: float | None = None,
                 strip_rows: int | None = None) -> None:
        self.sink = sink
        self.strip_delay_s = (CONFIG.screen_strip_delay_ms / 1000.0
                              if strip_delay_s is None else float(strip_delay_s))
        self.strip_rows = (CONFIG.screen_strip_rows if strip_rows is None
                           else int(strip_rows))
        self._frame_id = 0
        self.chunks_sent = 0

    # ---- frame ids ----------------------------------------------------------------
    def next_frame_id(self) -> int:
        """Rolling u8. Groups the chunks of one logical frame."""
        self._frame_id = (self._frame_id + 1) & 0xFF
        return self._frame_id

    # ---- drivers -----------------------------------------------------------------
    def send_payloads(self, payloads: Iterable[bytes], delay_s: float | None = None) -> int:
        """Send in order with a gap between chunks. Returns how many went out."""
        gap = self.strip_delay_s if delay_s is None else float(delay_s)
        n = 0
        for i, payload in enumerate(payloads):
            if i and gap > 0:
                time.sleep(gap)
            self.sink.send(MsgType.SCREEN_FRAME, payload)
            n += 1
        self.chunks_sent += n
        return n

    async def asend_payloads(self, payloads: Iterable[bytes],
                             delay_s: float | None = None) -> int:
        gap = self.strip_delay_s if delay_s is None else float(delay_s)
        n = 0
        for i, payload in enumerate(payloads):
            if i and gap > 0:
                await asyncio.sleep(gap)
            self.sink.send(MsgType.SCREEN_FRAME, payload)
            n += 1
        self.chunks_sent += n
        return n

    # ---- text --------------------------------------------------------------------
    def send_text(self, text: str, row: int = 0, scale: int = 2,
                  fg: int = RGB565_WHITE, bg: int = RGB565_BLACK,
                  clear: bool = False) -> int:
        """One line on one row. The common case for a quick message."""
        return self.send_lines([text], start_row=row, scale=scale, fg=fg, bg=bg,
                               clear=clear)

    def send_lines(self, lines: Sequence[str], *, start_row: int = 0, scale: int = 2,
                   fg: int = RGB565_WHITE, bg: int = RGB565_BLACK,
                   clear: bool = False) -> int:
        payloads = text_payloads(lines, start_row=start_row, scale=scale, fg=fg, bg=bg,
                                 frame_id=self.next_frame_id(), clear=clear)
        # Text chunks are tiny (<= 67-byte payloads) and there are at most 10; the queue
        # depth of 4 is still the constraint, so keep a small gap but not the strip gap.
        return self.send_payloads(payloads, delay_s=min(self.strip_delay_s, 0.002))

    async def asend_lines(self, lines: Sequence[str], *, start_row: int = 0,
                          scale: int = 2, fg: int = RGB565_WHITE, bg: int = RGB565_BLACK,
                          clear: bool = False) -> int:
        payloads = text_payloads(lines, start_row=start_row, scale=scale, fg=fg, bg=bg,
                                 frame_id=self.next_frame_id(), clear=clear)
        return await self.asend_payloads(payloads,
                                         delay_s=min(self.strip_delay_s, 0.002))

    # ---- pixels ------------------------------------------------------------------
    def send_rgb565(self, pixels565: bytes, *, w: int = SCREEN_W, h: int = SCREEN_H,
                    x0: int = 0, y0: int = 0, clear: bool = True) -> int:
        payloads = image_payloads(pixels565, w=w, h=h, x0=x0, y0=y0,
                                  frame_id=self.next_frame_id(),
                                  strip_rows=self.strip_rows, clear=clear)
        return self.send_payloads(payloads)

    async def asend_rgb565(self, pixels565: bytes, *, w: int = SCREEN_W, h: int = SCREEN_H,
                           x0: int = 0, y0: int = 0, clear: bool = True) -> int:
        payloads = image_payloads(pixels565, w=w, h=h, x0=x0, y0=y0,
                                  frame_id=self.next_frame_id(),
                                  strip_rows=self.strip_rows, clear=clear)
        return await self.asend_payloads(payloads)

    def send_frame(self, img, *, clear: bool = True) -> int:
        """Send a PIL image. Letterboxed to 320x240 first if it is not already."""
        from .frames import PANEL_SIZE, image_to_rgb565, letterbox

        if img.size != PANEL_SIZE:
            img = letterbox(img)
        return self.send_rgb565(image_to_rgb565(img), clear=clear)

    async def asend_frame(self, img, *, clear: bool = True) -> int:
        from .frames import PANEL_SIZE, image_to_rgb565, letterbox

        if img.size != PANEL_SIZE:
            img = letterbox(img)
        return await self.asend_rgb565(image_to_rgb565(img), clear=clear)

    def send_image_file(self, path, *, clear: bool = True) -> int:
        """Load an image file from disk and send it."""
        from .frames import file_to_rgb565

        return self.send_rgb565(file_to_rgb565(path), clear=clear)

    # ---- panel ownership ---------------------------------------------------------
    def release(self) -> int:
        """Hand the panel straight back to the drone's own status screen.

        Without this the drone keeps showing the last frame for 5 s after the stream
        stops, which looks like a hang rather than a handover.
        """
        self.sink.send(MsgType.SCREEN_FRAME, screen_status_payload(self.next_frame_id()))
        self.chunks_sent += 1
        return 1
