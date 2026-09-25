"""`kogane-screen` — drive the drone's panel by hand.

Standalone: it opens its own UDP socket and needs no base station running, which is the
point. When the drone is on the bench or in the air and you want the display to say
something, this is the thing you type.

    kogane-screen --text "hello there"
    kogane-screen --text "KOGANE" --row 0 --scale 3 --text "tracking sujay" --row 2
    kogane-screen --image assets/face.png
    kogane-screen --demo
    kogane-screen --status                 # hand the panel back to the drone

Remember the 5 s rule from PROTOCOL.md §1: after the last non-STATUS chunk the drone keeps
your frame for five seconds and then takes the panel back on its own. `--hold` just sleeps,
re-sending nothing, if you want to watch that happen; `--status` skips the wait.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..config import CONFIG
from ..net.sink import SocketSink
from ..protocol import (RGB565_BLACK, RGB565_WHITE, SCREEN_TEXT_MAX, SCREEN_TEXT_ROWS,
                        SCREEN_TEXT_SCALE_MAX, rgb565)
from ..screen.sender import ScreenSender

log = logging.getLogger("kogane.screen.cli")

_NAMED = {
    "black": 0x0000, "white": 0xFFFF, "red": 0xF800, "green": 0x07E0, "blue": 0x001F,
    "cyan": 0x07FF, "magenta": 0xF81F, "yellow": 0xFFE0, "amber": 0xFD20, "grey": 0x8410,
    "gray": 0x8410,
}


def parse_colour(raw: str) -> int:
    """`red`, `0xF800`, `#ff8800` or `255,136,0` -> an RGB565 u16."""
    s = raw.strip().lower()
    if s in _NAMED:
        return _NAMED[s]
    if s.startswith("#"):
        if len(s) != 7:
            raise argparse.ArgumentTypeError(f"expected #rrggbb; got {raw!r}")
        return rgb565(int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
    if "," in s:
        parts = [p for p in s.split(",") if p.strip()]
        if len(parts) != 3:
            raise argparse.ArgumentTypeError(f"expected 'r,g,b'; got {raw!r}")
        return rgb565(*(int(p) for p in parts))
    try:
        value = int(s, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"unknown colour {raw!r}; try a name ({', '.join(sorted(_NAMED))}), "
            "0xF800, #ff8800 or 255,136,0") from None
    if not 0 <= value <= 0xFFFF:
        raise argparse.ArgumentTypeError(f"RGB565 is a u16; got {raw!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kogane-screen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Send SCREEN_FRAME (0x30) updates to the drone's 320x240 panel.",
        epilog="examples:\n"
               "  kogane-screen --text \"hello there\"\n"
               "  kogane-screen --text KOGANE --scale 3 --text \"link up\" --row 2\n"
               "  kogane-screen --image photo.jpg\n"
               "  kogane-screen --demo --hold 6\n"
               "  kogane-screen --status\n")
    ap.add_argument("--host", default=CONFIG.drone_ip,
                    help=f"drone address (default {CONFIG.drone_ip}, from KGN_DRONE_IP)")
    ap.add_argument("--port", type=int, default=CONFIG.udp_port,
                    help=f"drone UDP port (default {CONFIG.udp_port})")

    ap.add_argument("--text", action="append", default=[], metavar="STR",
                    help=f"a line of text, max {SCREEN_TEXT_MAX} chars. Repeatable; each "
                         "one lands on the next row unless --row is given again")
    ap.add_argument("--row", action="append", default=[], type=int, metavar="N",
                    help=f"row 0..{SCREEN_TEXT_ROWS - 1} for the matching --text")
    ap.add_argument("--scale", type=int, default=2,
                    help=f"glyph scale 1..{SCREEN_TEXT_SCALE_MAX} (default 2)")
    ap.add_argument("--fg", type=parse_colour, default=RGB565_WHITE, help="text colour")
    ap.add_argument("--bg", type=parse_colour, default=RGB565_BLACK,
                    help="row background colour")

    ap.add_argument("--image", metavar="PATH", help="send an image file, letterboxed to "
                                                   "320x240")
    ap.add_argument("--demo", action="store_true",
                    help="send a composed PIL frame (title, rings, colour bars)")
    ap.add_argument("--status", action="store_true",
                    help="release the panel back to the drone's own status screen")

    ap.add_argument("--clear", action="store_true",
                    help="set FIRST so the drone blanks the panel before drawing text")
    ap.add_argument("--strip-rows", type=int, default=CONFIG.screen_strip_rows,
                    help=f"image strip height (default {CONFIG.screen_strip_rows}; "
                         "320x2 px = 1280 bytes, the largest that fits a datagram)")
    ap.add_argument("--strip-delay-ms", type=float, default=CONFIG.screen_strip_delay_ms,
                    help=f"gap between strips (default {CONFIG.screen_strip_delay_ms:g}; "
                         "the drone's display queue is only 4 deep)")
    ap.add_argument("--hold", type=float, default=0.0, metavar="S",
                    help="sleep this long after sending, before exiting")
    ap.add_argument("--repeat", type=int, default=1,
                    help="send the frame N times (useful over a lossy link)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and report the chunks without opening a socket")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def _pair_text_rows(texts: list[str], rows: list[int]) -> list[tuple[int, str]]:
    """Match each --text with its --row, defaulting to consecutive rows from 0."""
    out: list[tuple[int, str]] = []
    for i, text in enumerate(texts):
        row = rows[i] if i < len(rows) else (out[-1][0] + 1 if out else 0)
        out.append((row, text))
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

    if not (args.text or args.image or args.demo or args.status):
        build_parser().print_help()
        print("\nnothing to send: pass --text, --image, --demo or --status",
              file=sys.stderr)
        return 2

    from ..net.sink import ListSink

    sink = (ListSink() if args.dry_run
            else SocketSink(args.host, args.port))
    dest = "(dry run)" if args.dry_run else f"{args.host}:{args.port}"
    sender = ScreenSender(sink, strip_delay_s=args.strip_delay_ms / 1000.0,
                          strip_rows=args.strip_rows)
    rc = 0
    try:
        for attempt in range(max(1, args.repeat)):
            if attempt:
                time.sleep(0.25)
            rc = _send_once(args, sender, dest) or rc
    except KeyboardInterrupt:
        print()
        return 130
    except FileNotFoundError as e:
        print(f"FAILED: no such file: {e.filename}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        if isinstance(sink, SocketSink):
            sink.close()

    if args.hold > 0:
        print(f"holding {args.hold:g}s (the drone reclaims the panel 5 s after the last "
              f"chunk)")
        try:
            time.sleep(args.hold)
        except KeyboardInterrupt:
            print()
    return rc


def _send_once(args, sender: ScreenSender, dest: str) -> int:
    if args.status:
        sender.release()
        print(f"-> {dest}  STATUS: panel released to the drone's own status screen")
        return 0

    total = 0
    if args.text:
        for row, text in _pair_text_rows(args.text, args.row):
            if not 0 <= row < SCREEN_TEXT_ROWS:
                print(f"FAILED: row {row} is outside 0..{SCREEN_TEXT_ROWS - 1}",
                      file=sys.stderr)
                return 1
            n = sender.send_text(text, row=row, scale=args.scale, fg=args.fg, bg=args.bg,
                                 clear=args.clear)
            total += n
            # ASCII only in the echo: this gets read off a terminal on camera, and a
            # console on cp1252 turns a real ellipsis into mojibake.
            if len(text) <= SCREEN_TEXT_MAX:
                shown = repr(text)
            else:
                shown = (f"{text[:SCREEN_TEXT_MAX]!r} (truncated, "
                         f"{len(text) - SCREEN_TEXT_MAX} char(s) dropped)")
            print(f"-> {dest}  TEXT row {row} scale {args.scale}: {shown}")

    if args.demo:
        from ..screen.frames import compose_demo

        img = compose_demo(subtitle=f"{dest}")
        t0 = time.monotonic()
        n = sender.send_frame(img)
        total += n
        print(f"-> {dest}  DEMO frame: {n} strip(s) in {time.monotonic() - t0:.2f}s")

    if args.image:
        from ..screen.frames import load_image

        img = load_image(args.image)
        print(f"   {args.image}: {img.size[0]}x{img.size[1]} -> letterboxed to 320x240")
        t0 = time.monotonic()
        n = sender.send_frame(img)
        total += n
        print(f"-> {dest}  IMAGE: {n} strip(s) in {time.monotonic() - t0:.2f}s")

    wire = getattr(sender.sink, "sent_bytes", None)
    print(f"   {total} SCREEN_FRAME chunk(s) sent"
          + (f", {wire} bytes of UDP payload" if wire else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
