"""Record a short stationary ESP32 microphone check, without laptop capture."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import threading
import time

import numpy as np

from ..audio.esp_mic import EspMicInput
from ..audio.wav import write_wav

BASE = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="ESP32 Wi-Fi IP")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--listen-port", type=int, default=5005)
    parser.add_argument("--seconds", type=float, default=12)
    parser.add_argument("--output", type=Path, help="new WAV path; default outputs/board_mic/<timestamp>.wav")
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 3 <= args.seconds <= 60:
        raise ValueError("Recording duration must be between 3 and 60 seconds")
    output = args.output or BASE/"outputs/board_mic"/(datetime.now().strftime("board_%Y%m%d_%H%M%S_%f")+".wav")
    if output.exists() or output.with_suffix(".json").exists():
        raise FileExistsError("Choose a new --output path to preserve the previous recording")
    pieces, byte_count = [], 0
    limit = round(args.seconds*16000)*2
    lock = threading.Lock()

    def capture(pcm, reset):
        nonlocal byte_count
        with lock:
            pcm = pcm[:max(0, limit-byte_count)]
            pieces.append(pcm)
            byte_count += len(pcm)

    print("Waiting for board microphone audio…", flush=True)
    try:
        with EspMicInput(args.host, capture, port=args.port, listen_port=args.listen_port) as source:
            source.wait_ready()
            print(f"Recording {args.seconds:g}s. Speak near the board; leave motors off.", flush=True)
            start = time.monotonic()
            while time.monotonic()-start < args.seconds:
                source.check_health()
                time.sleep(.05)
        with lock:
            audio = np.frombuffer(b"".join(pieces), dtype="<i2").copy()
        if not audio.size:
            raise RuntimeError("No microphone samples received")
        write_wav(output, audio)
        values = audio.astype(float)
        report = dict(source="esp32", host=args.host, sample_rate=16000,
                      duration_s=audio.size/16000, requested_s=args.seconds,
                      peak=int(np.max(np.abs(values))), rms=float(np.sqrt(np.mean(values**2))),
                      clipped_fraction=float(np.mean(np.abs(values) >= 32767)),
                      stream=source.stats, wav=str(output.resolve()),
                      verification="Audio received; listen to verify speech clarity")
        output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        print("Board stream OFF requested. Play the WAV and check your speech before testing commands.", flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Board microphone check failed: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
