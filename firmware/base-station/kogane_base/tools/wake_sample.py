"""Record a bounded local pronunciation sample and inspect offline recognition.

Does not contact the FC, upload audio, train a model, or auto-enable wake aliases.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import wave

import numpy as np

from ..audio.wav import pcm_to_bytes, to_kgn_pcm
from .demo_assistant import BASE, WAKE_ALIASES, SpeechDecoder, load_wake_profile


def record_sample(path, seconds=20, device=None):
    import sounddevice as sd
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Choose a new sample filename; {path} already exists")
    samples = round(seconds*16000)
    blocks = []
    with sd.RawInputStream(samplerate=16000, blocksize=1600, device=device,
                           dtype="int16", channels=1) as stream:
        while samples:
            count = min(1600, samples)
            data, overflow = stream.read(count)
            if overflow:
                raise RuntimeError("Microphone input overflowed; close busy programs and record again")
            blocks.append(bytes(data))
            samples -= count
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"".join(blocks))
    return path


def decode_audio(model, pcm, grammar=None):
    from vosk import KaldiRecognizer
    rec = (KaldiRecognizer(model, 16000, grammar) if grammar else
           KaldiRecognizer(model, 16000))
    rec.SetWords(True)
    data = pcm_to_bytes(pcm)+b"\0\0"*16000
    results = []
    for start in range(0, len(data), 3200):
        if rec.AcceptWaveform(data[start:start+3200]):
            result = json.loads(rec.Result())
            if result.get("text"):
                results.append(result)
    final = json.loads(rec.FinalResult())
    if final.get("text"):
        results.append(final)
    return results


def analyze_sample(path, model_path):
    from vosk import Model, SetLogLevel
    pcm = to_kgn_pcm(Path(path))
    if len(pcm) == 0 or len(pcm) > 120*16000:
        raise ValueError("Use a nonempty recording no longer than two minutes")
    SetLogLevel(-1)
    model = Model(str(model_path))
    unconstrained = decode_audio(model, pcm)
    aliases, thresholds = load_wake_profile()
    decoder = SpeechDecoder(model, (*WAKE_ALIASES, *aliases), thresholds=thresholds)
    events, constrained, names, general = [], [], [], []
    data = pcm_to_bytes(pcm)+b"\0\0"*32000
    for start in range(0, len(data), 3200):
        events.extend(decoder.feed(data[start:start+3200], (start+3200)/32000))
        for mode, result in decoder.results:
            if result.get("text"):
                {"joint": constrained, "name": names, "command": general}[mode].append(result)
    values = pcm.astype(np.float64)
    return dict(audio=str(Path(path).resolve()), duration_s=len(pcm)/16000,
                peak_fraction=float(np.max(np.abs(values))/32768),
                rms_fraction=float(np.sqrt(np.mean(values*values))/32768),
                clipped_fraction=float(np.mean(np.abs(values) >= 32760)),
                unconstrained=unconstrained, wake_grammar=constrained,
                wake_name_grammar=names, general_commands=general, events=events,
                wake_thresholds=thresholds,
                input_processing=dict(highpass_hz=80, gain=4, decoder="name-fixed-and-general-command"),
                note="Pronunciation diagnostic only. No model training or automatic alias adoption.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--device", type=int, help="same laptop input index as demo_assistant")
    p.add_argument("--out", type=Path, help="new WAV filename; existing samples are never overwritten")
    p.add_argument("--analyze", type=Path, help="analyze an existing WAV without opening the microphone")
    p.add_argument("--model", type=Path, default=BASE/"models/vosk-model-small-en-us-0.15")
    p.add_argument("--no-analysis", action="store_true", help="record and save only")
    args = p.parse_args(argv)
    if not math.isfinite(args.seconds) or not 5 <= args.seconds <= 60:
        p.error("--seconds must be between 5 and 60")
    path = args.analyze
    if path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = args.out or BASE/"outputs/wake_samples"/f"kogane_{stamp}.wav"
        if path.exists():
            p.error(f"{path} exists; choose a new --out filename")
        print("Close the assistant first. Say Kogane naturally 5–6 times, with about 2 seconds between repetitions.", flush=True)
        print(f"Recording for {args.seconds:g} seconds after the countdown. Audio stays on this laptop.", flush=True)
        for count in (3, 2, 1):
            print(count, flush=True)
            time.sleep(1)
        print("RECORDING — start speaking now", flush=True)
        record_sample(path, args.seconds, args.device)
        print(f"Saved: {path.resolve()}", flush=True)
    if args.no_analysis:
        return 0
    report = analyze_sample(path, args.model)
    destination = path.with_suffix(".recognition.json")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name in ("unconstrained", "wake_grammar", "wake_name_grammar", "general_commands"):
        print(name+":", flush=True)
        for result in report.get(name, []):
            print("  "+repr(result["text"]), flush=True)
    print(f"Wake detections in this sample: {sum(event[0] == 'wake' for event in report['events'])}", flush=True)
    print(f"Recognition report: {destination.resolve()}", flush=True)
    print("Share the WAV or the recognition report to tune the name; no model has been trained or changed.", flush=True)
    if report["peak_fraction"] < .01:
        print("Recording is very quiet; check the selected microphone.")
    if report["clipped_fraction"] > .001:
        print("Recording contains clipping; move farther from the mic or reduce input gain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
