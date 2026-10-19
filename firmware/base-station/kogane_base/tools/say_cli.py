"""`kogane-say` — speak text through the laptop's default speaker.

Windows SAPI renders the text to a 16 kHz mono WAV (the exact format `fmt = 1` fixes on the
wire, so nothing is resampled). The normal path plays that WAV locally. `--drone`
keeps the old AUDIO_TTS path available if the drone amplifier is repaired.
No pip install, no cloud key, no API quota.

    kogane-say "hello, I am kogane"
    kogane-say "following you now" --voice Zira --rate 2
    kogane-say "testing" --keep out.wav
    kogane-say "testing" --drone --host 192.168.1.123
    kogane-say --list-voices

`--screen` is the demo flourish: put the same words on the panel while they are spoken.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import time

from ..audio.sender import AudioSender
from ..audio.tts import SapiTts, TtsError, TtsUnavailable
from ..audio.wav import to_kgn_pcm, wav_probe
from ..config import CONFIG
from ..net.sink import SocketSink
from ..protocol import AUDIO_RATE_HZ, RGB565_AMBER, RGB565_WHITE

log = logging.getLogger("kogane.say")

# The panel is 53 chars per row at scale 1 and half that at scale 2, so long sentences get
# split across rows for --screen rather than truncated.
_SCREEN_COLS = 26
_SCREEN_ROWS = 4


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kogane-say",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Synthesise speech with Windows SAPI and play it on this laptop.",
        epilog="examples:\n"
               "  kogane-say \"hello, I am kogane\"\n"
               "  kogane-say \"following you now\" --voice Zira --rate 2 --screen\n"
               "  kogane-say --list-voices\n"
               "  kogane-say \"check\" --keep check.wav --no-send\n")
    ap.add_argument("text", nargs="*", help="what to say (joined with spaces)")
    ap.add_argument("--host", default=CONFIG.drone_ip,
                    help=f"drone address (default {CONFIG.drone_ip}, from KGN_DRONE_IP)")
    ap.add_argument("--port", type=int, default=CONFIG.udp_port,
                    help=f"drone UDP port (default {CONFIG.udp_port})")
    ap.add_argument("--voice", default=CONFIG.tts_voice,
                    help="installed SAPI voice, matched as a substring (see --list-voices)")
    ap.add_argument("--rate", type=int, default=CONFIG.tts_rate,
                    help="SAPI speaking rate, -10..10 (0 = normal)")
    ap.add_argument("--list-voices", action="store_true",
                    help="print the SAPI voices installed on this machine and exit")
    ap.add_argument("--keep", metavar="OUT.WAV",
                    help="also keep the synthesised WAV at this path")
    ap.add_argument("--no-send", action="store_true",
                    help="synthesise only; do not play or use the network")
    ap.add_argument("--drone", action="store_true",
                    help="send audio to the drone instead of the laptop speaker")
    ap.add_argument("--screen", action="store_true",
                    help="also show the text on the drone's panel while it is spoken")
    ap.add_argument("--chunk-ms", type=float, default=CONFIG.audio_chunk_ms,
                    help=f"PCM chunk length (default {CONFIG.audio_chunk_ms:g} ms)")
    ap.add_argument("--lead-ms", type=float, default=CONFIG.audio_lead_ms,
                    help=f"how far ahead of real time to run (default "
                         f"{CONFIG.audio_lead_ms:g} ms)")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def wrap_for_panel(text: str, cols: int = _SCREEN_COLS,
                   rows: int = _SCREEN_ROWS) -> list[str]:
    """Greedy word wrap into at most `rows` lines of `cols` characters."""
    out: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) <= cols:
            line = candidate
            continue
        if line:
            out.append(line)
        line = word[:cols]
        if len(out) >= rows:
            break
    if line and len(out) < rows:
        out.append(line)
    return out[:rows]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

    tts = SapiTts(voice=args.voice, rate=args.rate)

    if args.list_voices:
        return _list_voices(tts)

    text = " ".join(args.text).strip()
    if not text:
        build_parser().print_help()
        print("\nnothing to say: pass some text", file=sys.stderr)
        return 2

    tmp_path: str | None = None
    if args.keep:
        wav_path = args.keep
    else:
        fd, tmp_path = tempfile.mkstemp(prefix="kgn-say-", suffix=".wav")
        os.close(fd)
        wav_path = tmp_path

    try:
        print(f"   synthesising {len(text)} char(s) with SAPI "
              f"({args.voice or 'default voice'}, rate {args.rate})")
        t0 = time.monotonic()
        try:
            tts.synthesise(text, wav_path)
        except TtsUnavailable as e:
            print(f"FAILED: text-to-speech is not available here.\n  {e}", file=sys.stderr)
            return 3
        except TtsError as e:
            print(f"FAILED: synthesis failed.\n  {e}", file=sys.stderr)
            return 3

        info = wav_probe(wav_path)
        ok = (info.rate == AUDIO_RATE_HZ and info.channels == 1
              and info.sample_width == 2)
        print(f"   {info.describe()} in {time.monotonic() - t0:.2f}s"
              f"  [{'matches fmt=1 exactly' if ok else 'will be converted'}]"
              f"  voice={tts.last_voice or 'default'}")
        if args.keep:
            print(f"   kept {args.keep}")

        if args.no_send:
            return 0

        if not args.drone:
            if args.screen:
                dest = f"{args.host}:{args.port}"
                with SocketSink(args.host, args.port) as sink:
                    _push_screen(sink, text, dest)
            _play_local(wav_path)
            print(f"   played on laptop: {text!r}")
            return 0

        dest = f"{args.host}:{args.port}"
        with SocketSink(args.host, args.port) as sink:
            if args.screen:
                _push_screen(sink, text, dest)
            sender = AudioSender(sink, chunk_ms=args.chunk_ms, lead_ms=args.lead_ms)
            pcm = to_kgn_pcm(wav_path)
            n_chunks = max(1, -(-pcm.size * 2 // sender.chunk_bytes))
            print(f"-> {dest}  AUDIO_TTS: {pcm.size / AUDIO_RATE_HZ:.2f} s in "
                  f"{n_chunks} chunk(s) of {sender.chunk_ms:g} ms, paced to real time")
            t1 = time.monotonic()
            sent = sender.stream_pcm(pcm)
            print(f"   {sent} chunk(s) in {time.monotonic() - t1:.2f}s — "
                  f"said: {text!r}")
        return 0
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _play_local(wav_path: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("laptop speaker playback currently requires Windows")
    import winsound
    winsound.PlaySound(wav_path, winsound.SND_FILENAME)


def _push_screen(sink, text: str, dest: str) -> None:
    from ..screen.sender import ScreenSender

    lines = ["KOGANE SAYS"] + wrap_for_panel(text)
    screen = ScreenSender(sink)
    screen.send_lines(lines[:1], start_row=0, scale=2, fg=RGB565_AMBER, clear=True)
    if len(lines) > 1:
        screen.send_lines(lines[1:], start_row=2, scale=2, fg=RGB565_WHITE)
    print(f"-> {dest}  SCREEN: {len(lines)} text row(s)")


def _list_voices(tts: SapiTts) -> int:
    try:
        rows = tts.voices()
    except TtsUnavailable as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 3
    except TtsError as e:
        print(f"FAILED: could not list voices: {e}", file=sys.stderr)
        return 3
    if not rows:
        print("no SAPI voices installed", file=sys.stderr)
        return 3
    width = max(len(name) for name, _, _, _ in rows)
    print(f"{'VOICE'.ljust(width)}  CULTURE  GENDER  ENABLED")
    for name, culture, gender, enabled in rows:
        print(f"{name.ljust(width)}  {culture:<7}  {gender:<6}  "
              f"{'yes' if enabled else 'no'}")
    print("\npass any substring to --voice, e.g. --voice Zira")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
