"""Throwaway end-to-end check: run the real CLIs at a local UDP socket and decode what
arrives, acting as the firmware would. Deleted after the verification run."""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time

from kogane_base import protocol as p

PY = sys.executable


def listen(port_holder, frames, stop):
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
    rx.bind(("127.0.0.1", 0))
    port_holder.append(rx.getsockname()[1])
    rx.settimeout(0.3)
    while not stop.is_set():
        try:
            data, _ = rx.recvfrom(2048)
        except OSError:
            continue
        frames.append((len(data), p.unpack(data)))
    rx.close()


def run(args):
    print(f"\n$ {' '.join(args[2:])}")
    r = subprocess.run([PY, "-m", *args[1:]], capture_output=True, text=True)
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print("stderr:", r.stderr.rstrip())
    print(f"exit={r.returncode}")
    return r.returncode


def main() -> int:
    ports, frames, stop = [], [], threading.Event()
    t = threading.Thread(target=listen, args=(ports, frames, stop), daemon=True)
    t.start()
    while not ports:
        time.sleep(0.01)
    port = ports[0]
    host = ["--host", "127.0.0.1", "--port", str(port)]
    bad = 0

    def checkpoint(label, expect_types):
        time.sleep(0.5)
        got = list(frames)
        frames.clear()
        nonlocal bad
        malformed = sum(1 for _, f in got if f is None)
        types = {}
        maxlen = 0
        for n, f in got:
            maxlen = max(maxlen, n)
            if f is not None:
                types[f.msg_type] = types.get(f.msg_type, 0) + 1
        print(f"  RX {label}: {len(got)} datagram(s), max {maxlen} bytes, "
              f"malformed {malformed}, types "
              f"{ {p.MsgType(k).name: v for k, v in types.items()} }")
        if malformed:
            bad += 1
            print("  !! malformed datagrams")
        if set(types) != set(int(t) for t in expect_types):
            bad += 1
            print(f"  !! expected {expect_types}")
        return got

    # --- screen: text
    run(["-m", "kogane_base.tools.screen_cli", *host, "--text", "KOGANE",
         "--text", "link up", "--scale", "2", "--fg", "amber", "--clear"])
    got = checkpoint("screen text", [p.MsgType.SCREEN_FRAME])
    lines = [p.unpack_screen_text(f.payload) for _, f in got if f]
    print(f"     decoded rows: {[(l.row, l.text, l.scale, hex(l.fg)) for l in lines]}")
    assert [l.text for l in lines] == ["KOGANE", "link up"], lines
    assert p.unpack_screen_header(got[0][1].payload).flags & p.SF_F_FIRST

    # --- screen: demo image, 120 strips
    run(["-m", "kogane_base.tools.screen_cli", *host, "--demo",
         "--strip-delay-ms", "1"])
    got = checkpoint("screen demo", [p.MsgType.SCREEN_FRAME])
    tiles = [p.unpack_screen_tile(f.payload) for _, f in got if f]
    assert len(tiles) == 120 and all(t is not None for t in tiles), len(tiles)
    assert [t.y for t in tiles] == list(range(0, 240, 2))
    assert all(t.w == 320 and t.h == 2 and len(t.pixels) == 1280 for t in tiles)
    assert max(n for n, _ in got) == 1312, max(n for n, _ in got)
    print(f"     120 strips y=0..238, every tile 320x2, every datagram 1312 bytes")

    # --- screen: STATUS release
    run(["-m", "kogane_base.tools.screen_cli", *host, "--status"])
    got = checkpoint("screen status", [p.MsgType.SCREEN_FRAME])
    assert len(got) == 1 and len(got[0][1].payload) == 8
    assert p.unpack_screen_header(got[0][1].payload).flags & p.SF_F_STATUS
    print("     STATUS flag set on a bare 8-byte payload")

    # --- audio: CTRL
    run(["-m", "kogane_base.tools.audio_cli", *host, "--selftest", "--mic-on",
         "--mic-off", "--flush"])
    got = checkpoint("audio ctrl", [p.MsgType.AUDIO_TTS])
    cmds = [p.unpack_audio_chunk(f.payload).cmd for _, f in got if f]
    print(f"     ctrl cmds in send order: {[p.AudioCmd(c).name for c in cmds]}")
    assert sorted(cmds) == [1, 2, 3, 4], cmds

    # --- audio: paced tone
    t0 = time.monotonic()
    run(["-m", "kogane_base.tools.audio_cli", *host, "--tone", "--seconds", "1.0"])
    wall = time.monotonic() - t0
    got = checkpoint("audio tone", [p.MsgType.AUDIO_TTS])
    chunks = [p.unpack_audio_chunk(f.payload) for _, f in got if f]
    assert len(chunks) == 50, len(chunks)
    assert chunks[0].start and chunks[-1].end
    assert [c.seq for c in chunks] == list(range(50))
    total = sum(c.samples for c in chunks)
    assert total == 16000, total
    assert max(len(f.payload) - 4 for _, f in got if f) == 640
    print(f"     50 chunks, seq 0..49, START/END correct, {total} samples = 1.00 s of "
          f"audio, wall {wall:.2f}s (paced)")

    # --- say: real SAPI -> real datagrams
    rc = run(["-m", "kogane_base.tools.say_cli", *host,
              "hello, I am kogane, and I am following you", "--screen"])
    got = checkpoint("say", [p.MsgType.SCREEN_FRAME, p.MsgType.AUDIO_TTS])
    audio = [p.unpack_audio_chunk(f.payload) for _, f in got
             if f and f.msg_type == int(p.MsgType.AUDIO_TTS)]
    pcm = b"".join(c.pcm for c in audio)
    import numpy as np
    a = np.frombuffer(pcm, dtype="<i2")
    print(f"     {len(audio)} audio chunks, {a.size} samples = "
          f"{a.size / 16000:.2f}s, peak {int(np.abs(a).max())}, "
          f"rms {float(np.sqrt((a.astype(float)**2).mean())):.0f}")
    assert audio[0].start and audio[-1].end
    assert int(np.abs(a).max()) > 3000, "the received audio is silent"

    stop.set()
    t.join(timeout=2)
    print(f"\n{'FAILURES: ' + str(bad) if bad else 'ALL LOOPBACK CHECKS PASSED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
