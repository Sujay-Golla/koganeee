"""Make local voice samples without microphone, network or FC access."""
import argparse
from pathlib import Path
import shutil

from ..audio.character_voice import STYLES, render_speech

BASE = Path(__file__).resolve().parents[2]
SAMPLE_TEXT = "Hello! I'm Kogane. Your task is saved! Today's weather is clear, with a high of seventeen degrees."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=SAMPLE_TEXT)
    parser.add_argument("--output", type=Path, default=BASE/"outputs/voice_samples")
    parser.add_argument("--style", choices=STYLES, action="append", help="repeat to compare styles; default the four Windows styles")
    parser.add_argument("--voice", help="override the installed base voice")
    parser.add_argument("--rate", type=int, help="source speech rate, -10..10")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    for style in args.style or ("normal", "bright", "mascot", "electronic"):
        print(f"Preparing {style}…", flush=True)
        path = render_speech(args.text, args.output/"cache", style=style, voice=args.voice, rate=args.rate)
        sample = args.output/f"{style}.wav"
        shutil.copyfile(path, sample)
        print(f"{style}: {sample.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
