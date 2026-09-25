"""`kogane-audio` — drive the drone's speaker and microphone by hand.

Standalone, like `kogane-screen`: its own socket, no base station needed.

    kogane-audio --selftest            # the drone's own tone; proves the amp
    kogane-audio --tone                # a tone generated here; proves the link too
    kogane-audio --wav hello.wav       # any rate/channels, converted and streamed
    kogane-audio --flush               # stop playback immediately
    kogane-audio --mic-on
    kogane-audio --record mic.wav --seconds 5
    kogane-audio --mic-off

`--tone` versus `--selftest` is the useful split: SELFTEST is one CTRL byte and the drone
generates the sound itself, so if that works and `--tone` does not, the speaker is fine and
the problem is the network or the playback queue.

Streaming is paced to real time on purpose. The drone's queue holds 12 chunks and discards
the **oldest** on overflow, so a sender that outruns it loses the start of the audio, not
the end.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..audio.recorder import MicRecorder
from ..audio.sender import AudioSender
from ..audio.wav import chirp, to_kgn_pcm, wav_probe
from ..config import CONFIG
from ..net.sink import SocketSink
from ..protocol import AUDIO_RATE_HZ, MsgType, unpack

log = logging.getLogger("kogane.audio.cli")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kogane-audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Send AUDIO_TTS (0x40) to the drone speaker and receive AUDIO_MIC "
                    "(0x41) from its microphone.",
        epilog="examples:\n"
               "  kogane-audio --selftest\n"
               "  kogane-audio --tone --freq 880 --seconds 1.5\n"
               "  kogane-audio --wav hello.wav\n"
               "  kogane-audio --mic-on --record mic.wav --seconds 5 --mic-off\n")
    ap.add_argument("--host", default=CONFIG.drone_ip,
                    help=f"drone address (default {CONFIG.drone_ip}, from KGN_DRONE_IP)")
    ap.add_argument("--port", type=int, default=CONFIG.udp_port,
                    help=f"drone UDP port (default {CONFIG.udp_port})")

    ap.add_argument("--wav", metavar="PATH",
                    help="stream a WAV file (any rate/channel count; converted to "
                         f"{AUDIO_RATE_HZ} Hz mono int16)")
    ap.add_argument("--tone", action="store_true",
                    help="stream a locally generated test tone")
    ap.add_argument("--chirp", action="store_true",
                    help="stream the three-note sequence the drone's self-test uses")
    ap.add_argument("--freq", type=float, default=660.0, help="--tone frequency, Hz")
    ap.add_argument("--seconds", type=float, default=1.0,
                    help="--tone length, or --record duration")
    ap.add_argument("--amplitude", type=float, default=0.35,
                    help="--tone amplitude 0..1 (default 0.35; full scale is unpleasant)")

    ap.add_argument("--selftest", action="store_true",
                    help="CTRL SELFTEST: the drone plays its own tone sequence")
    ap.add_argument("--flush", action="store_true",
                    help="CTRL FLUSH: drop queued audio and go silent now")
    ap.add_argument("--mic-on", action="store_true",
                    help="CTRL MIC_ON: ask the drone to start streaming AUDIO_MIC")
    ap.add_argument("--mic-off", action="store_true",
                    help="CTRL MIC_OFF: stop the mic stream (the drone's boot default)")
    ap.add_argument("--record", metavar="OUT.WAV",
                    help="listen for AUDIO_MIC chunks and write them to a WAV")
    ap.add_argument("--listen-port", type=int, default=CONFIG.udp_port,
                    help="port to bind for --record. The drone sends to a *configured* "
                         f"base address, not back to our source port, so this is the base "
                         f"station's own KGN port (default {CONFIG.udp_port}) and not "
                         "necessarily --port")

    ap.add_argument("--chunk-ms", type=float, default=CONFIG.audio_chunk_ms,
                    help=f"outbound PCM chunk length (default {CONFIG.audio_chunk_ms:g}; "
                         "the 1440-byte cap is 45 ms)")
    ap.add_argument("--lead-ms", type=float, default=CONFIG.audio_lead_ms,
                    help=f"how far ahead of real time to run (default "
                         f"{CONFIG.audio_lead_ms:g})")
    ap.add_argument("--no-pace", action="store_true",
                    help="send as fast as the socket allows. Loopback testing only: "
                         "against a real drone this loses the start of the audio")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the chunks and report them without opening a socket")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

    actions = (args.wav, args.tone, args.chirp, args.selftest, args.flush,
               args.mic_on, args.mic_off, args.record)
    if not any(actions):
        build_parser().print_help()
        print("\nnothing to do: pass --wav/--tone/--selftest/--mic-on/--record/...",
              file=sys.stderr)
        return 2

    from ..net.sink import ListSink

    if args.dry_run:
        sink = ListSink()
    else:
        # Bind only when we need to hear the drone back, so this tool can run alongside a
        # base station that already owns the KGN port.
        sink = SocketSink(args.host, args.port, recv=bool(args.record),
                          bind_port=args.listen_port)
    dest = "(dry run)" if args.dry_run else f"{args.host}:{args.port}"

    try:
        sender = AudioSender(sink, chunk_ms=args.chunk_ms, lead_ms=args.lead_ms)
    except ValueError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 2

    try:
        # Order is deliberate so `--mic-on --record out.wav --mic-off` reads left to right
        # and does the obvious thing.
        if args.flush:
            sender.flush()
            print(f"-> {dest}  CTRL FLUSH")
        if args.selftest:
            sender.selftest()
            print(f"-> {dest}  CTRL SELFTEST (the drone generates this tone itself)")
        if args.mic_on:
            sender.mic_on()
            print(f"-> {dest}  CTRL MIC_ON")

        if args.tone:
            _stream_tone(args, sender, dest)
        if args.chirp:
            pcm = chirp(amplitude=args.amplitude)
            _stream(args, sender, dest, pcm, f"CHIRP 660/880/1320 Hz")
        if args.wav:
            _stream_wav(args, sender, dest)

        rc = 0
        if args.record:
            rc = _record(args, sink, dest)

        if args.mic_off:
            sender.mic_off()
            print(f"-> {dest}  CTRL MIC_OFF")
        return rc
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


def _stream_tone(args, sender: AudioSender, dest: str) -> None:
    from ..audio.wav import tone

    pcm = tone(args.freq, args.seconds, amplitude=args.amplitude)
    _stream(args, sender, dest, pcm, f"TONE {args.freq:g} Hz {args.seconds:g}s")


def _stream_wav(args, sender: AudioSender, dest: str) -> None:
    info = wav_probe(args.wav)
    print(f"   {info.describe()}")
    pcm = to_kgn_pcm(args.wav)
    if info.rate != AUDIO_RATE_HZ or info.channels != 1:
        print(f"   converted to {AUDIO_RATE_HZ} Hz mono: {pcm.size} samples "
              f"({pcm.size / AUDIO_RATE_HZ:.2f} s)")
    _stream(args, sender, dest, pcm, f"WAV {args.wav}")


def _stream(args, sender: AudioSender, dest: str, pcm, label: str) -> None:
    n_chunks = max(1, -(-pcm.size * 2 // sender.chunk_bytes))
    print(f"-> {dest}  {label}: {pcm.size} samples, {pcm.size / AUDIO_RATE_HZ:.2f} s, "
          f"{n_chunks} chunk(s) of {sender.chunk_ms:g} ms"
          + ("  [UNPACED]" if args.no_pace else f"  lead {args.lead_ms:g} ms"))
    t0 = time.monotonic()
    sent = sender.stream_pcm(pcm, realtime=not args.no_pace)
    wall = time.monotonic() - t0
    audio_s = pcm.size / AUDIO_RATE_HZ
    print(f"   {sent} chunk(s) in {wall:.2f}s wall for {audio_s:.2f}s of audio "
          f"({'real time' if abs(wall - audio_s) < 0.35 else f'{audio_s / max(wall, 1e-6):.1f}x'})")
    if args.no_pace and audio_s > 0.4:
        print("   WARNING: unpaced. A real drone queues 12 chunks and drops the OLDEST, "
              "so the start of this would be lost.", file=sys.stderr)


def _record(args, sink, dest: str) -> int:
    if not isinstance(sink, SocketSink):
        print("   --record needs a real socket; --dry-run has nothing to listen to",
              file=sys.stderr)
        return 2
    rec = MicRecorder()
    deadline = time.monotonic() + max(0.1, args.seconds)
    sink.sock.settimeout(0.5)
    print(f"<- udp/{sink.bound_port}  listening for AUDIO_MIC for {args.seconds:g}s "
          f"(the drone only sends this after CTRL MIC_ON)")
    others = 0
    while time.monotonic() < deadline:
        try:
            data, _addr = sink.sock.recvfrom(2048)
        except OSError:
            continue
        frame = unpack(data)
        if frame is None:
            continue
        if frame.msg_type != MsgType.AUDIO_MIC:
            others += 1
            continue
        rec.on_payload(frame.payload)

    print(f"   {rec.stats.describe()}"
          + (f", {others} other KGN frame(s) ignored" if others else ""))
    if not rec.pcm:
        print("   NOTHING RECEIVED. The drone's mic is off until CTRL MIC_ON — try "
              "`kogane-audio --mic-on --record out.wav`.", file=sys.stderr)
        return 1
    out = rec.write_wav(args.record)
    print(f"   wrote {out} ({rec.buffered_s:.2f}s, {AUDIO_RATE_HZ} Hz mono 16-bit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
