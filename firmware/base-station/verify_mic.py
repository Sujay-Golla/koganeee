"""Throwaway: verify the AUDIO_MIC receive path and `kogane-audio --record` over loopback.

Pretends to be the drone: waits for CTRL MIC_ON, then streams 512-sample 0x41 blocks back,
the same shape audio_i2s.c sends. Deleted after the verification run.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

from kogane_base import protocol as p
from kogane_base.audio.wav import tone

DRONE_PORT = 45005      # where the drone listens (kogane-audio --port)
BASE_PORT = 45006       # the base station's own KGN port (kogane-audio --listen-port)
OUT = Path("verify_mic_out.wav")


def fake_drone(stop: threading.Event, report: list) -> None:
    """Bind the drone side, wait for MIC_ON, then stream mic audio to the configured base.

    Mirrors wifi_udp.c: outbound frames go to a *configured* base address, not back to
    whichever source port the CTRL arrived from.
    """
    drone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    drone.bind(("127.0.0.1", DRONE_PORT))
    drone.settimeout(0.3)
    streaming = False
    peer = None
    pcm = tone(880, 0.6).tobytes()
    blocks = [pcm[i:i + 1024] for i in range(0, len(pcm), 1024)]
    seq = 0
    while not stop.is_set():
        try:
            data, addr = drone.recvfrom(2048)
        except OSError:
            data = None
        if data:
            frame = p.unpack(data)
            if frame and frame.msg_type == int(p.MsgType.AUDIO_TTS):
                chunk = p.unpack_audio_chunk(frame.payload)
                if chunk and chunk.fmt == p.AudioFmt.CTRL:
                    name = p.AudioCmd(chunk.cmd).name
                    report.append(name)
                    if chunk.cmd == int(p.AudioCmd.MIC_ON):
                        streaming, peer, seq = True, ("127.0.0.1", BASE_PORT), 0
                    elif chunk.cmd == int(p.AudioCmd.MIC_OFF):
                        streaming = False
        if streaming and peer and seq < len(blocks):
            flags = (p.AU_F_START if seq == 0 else 0) | (
                p.AU_F_END if seq == len(blocks) - 1 else 0)
            drone.sendto(p.pack(p.MsgType.AUDIO_MIC,
                                p.audio_pcm_payload(blocks[seq], seq, flags), seq), peer)
            seq += 1
            time.sleep(0.032)          # 512 samples at 16 kHz, real time
    drone.close()


def main() -> int:
    OUT.unlink(missing_ok=True)
    stop, report = threading.Event(), []
    t = threading.Thread(target=fake_drone, args=(stop, report), daemon=True)
    t.start()
    time.sleep(0.2)

    cmd = [sys.executable, "-m", "kogane_base.tools.audio_cli",
           "--host", "127.0.0.1", "--port", str(DRONE_PORT),
           "--listen-port", str(BASE_PORT),
           "--mic-on", "--record", str(OUT), "--seconds", "2", "--mic-off"]
    print("$ " + " ".join(cmd[2:]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print("stderr:", r.stderr.rstrip())
    print(f"exit={r.returncode}")

    stop.set()
    t.join(timeout=2)
    print(f"  drone saw CTRL: {report}")

    ok = r.returncode == 0 and OUT.exists()
    if OUT.exists():
        with wave.open(str(OUT), "rb") as f:
            rate, ch, width, n = (f.getframerate(), f.getnchannels(),
                                  f.getsampwidth(), f.getnframes())
            a = np.frombuffer(f.readframes(n), dtype="<i2")
        print(f"  {OUT}: {rate} Hz, {ch} ch, {width * 8}-bit, {n} frames "
              f"({n / rate:.2f} s), peak {int(np.abs(a).max())}")
        ok = ok and (rate, ch, width) == (16000, 1, 2) and int(np.abs(a).max()) > 3000
        OUT.unlink()
    print("MIC PATH OK" if ok else "MIC PATH FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
