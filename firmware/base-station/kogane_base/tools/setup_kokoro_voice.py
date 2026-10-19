"""Download the optional free local voice model; no downloads during replies."""
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen

BASE = Path(__file__).resolve().parents[2]
ROOT = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
FILES = {
    "kokoro-v1.0.onnx": (325505369, "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}


def valid(path, size, digest):
    if not path.exists() or path.stat().st_size != size:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def main():
    folder = BASE/"models/kokoro-v1.0"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (size, digest) in FILES.items():
        output = folder/name
        if not valid(output, size, digest):
            pending = output.with_name(name+".part")
            print(f"Downloading {name} ({size/1e6:.1f} MB)…", flush=True)
            with urlopen(ROOT+name, timeout=30) as response, pending.open("wb") as stream:
                count = 0
                while block := response.read(1024*1024):
                    count += len(block)
                    if count > size:
                        raise RuntimeError(f"Unexpected download size for {name}")
                    stream.write(block)
            if not valid(pending, size, digest):
                raise RuntimeError(f"Download verification failed: {name}; run setup again")
            os.replace(pending, output)
        manifest[name] = dict(url=ROOT+name, size=size, sha256=digest)
        print(f"Verified {name}", flush=True)
    (folder/"source.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Ready. Try --speech-style mascot-lively", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
