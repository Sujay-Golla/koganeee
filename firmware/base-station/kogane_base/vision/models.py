"""Resolution and optional download of the small ONNX models OpenCV's face stack needs.

OpenCV ships the *code* for YuNet (detection) and SFace (recognition) inside
`cv2` itself — `cv2.FaceDetectorYN` and `cv2.FaceRecognizerSF`, verified present in
opencv-python 5.0.0 — but not the *weights*. Those live in the OpenCV Model Zoo, which
is Apache-2.0 licensed, and have to be fetched once.

Pinned filenames and their upstream source, for the record:

  face_detection_yunet_2023mar.onnx      ~227 KB
      https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
  face_recognition_sface_2021dec.onnx    ~37 MB
      https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface

The repo stores them via git-lfs, so the plain `raw.githubusercontent` URL hands back a
pointer file rather than an ONNX blob. The `media.githubusercontent.com/media/...` host
serves the real bytes, so that is tried first and the raw URL is only a fallback.

Nothing here runs at import time. Call `ensure_model` explicitly.
"""
from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("kogane.vision.models")

ZOO_LFS = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
ZOO_RAW = "https://github.com/opencv/opencv_zoo/raw/main/models"

# filename -> (zoo subdirectory, minimum plausible size in bytes)
MODEL_SOURCES: dict[str, tuple[str, int]] = {
    "face_detection_yunet_2023mar.onnx": ("face_detection_yunet", 100_000),
    "face_recognition_sface_2021dec.onnx": ("face_recognition_sface", 1_000_000),
}

_LFS_POINTER_PREFIX = b"version https://git-lfs"


class ModelMissingError(RuntimeError):
    """A required model file is absent and could not be fetched."""


def urls_for(filename: str) -> list[str]:
    entry = MODEL_SOURCES.get(filename)
    if entry is None:
        return []
    subdir, _min_size = entry
    return [f"{ZOO_LFS}/{subdir}/{filename}", f"{ZOO_RAW}/{subdir}/{filename}"]


def _min_size(filename: str) -> int:
    entry = MODEL_SOURCES.get(filename)
    return entry[1] if entry else 1


def _looks_valid(path: str, filename: str) -> bool:
    try:
        if os.path.getsize(path) < _min_size(filename):
            return False
        with open(path, "rb") as fh:
            return not fh.read(64).startswith(_LFS_POINTER_PREFIX)
    except OSError:
        return False


def download_model(filename: str, dest: str, timeout: float = 120.0) -> str:
    """Fetch one known model to `dest`. Raises ModelMissingError on failure."""
    if filename not in MODEL_SOURCES:
        raise ModelMissingError(f"unknown model {filename!r}; known: {sorted(MODEL_SOURCES)}")
    parent = os.path.dirname(os.path.abspath(dest))
    os.makedirs(parent, exist_ok=True)

    errors: list[str] = []
    for url in urls_for(filename):
        try:
            log.info("fetching %s from %s", filename, url)
            req = urllib.request.Request(url, headers={"User-Agent": "kogane-base/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if data[:64].startswith(_LFS_POINTER_PREFIX):
                errors.append(f"{url}: got a git-lfs pointer, not the model")
                continue
            if len(data) < _min_size(filename):
                errors.append(f"{url}: only {len(data)} bytes, expected >= {_min_size(filename)}")
                continue
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            log.info("saved %s (%d bytes)", dest, len(data))
            return dest
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            errors.append(f"{url}: {e!r}")

    raise ModelMissingError(
        f"could not download {filename}.\nTried:\n  " + "\n  ".join(errors) +
        f"\n\nFix it by hand:\n"
        f"  1. download {filename} from https://github.com/opencv/opencv_zoo\n"
        f"     (directory models/{MODEL_SOURCES[filename][0]}/)\n"
        f"  2. save it to {dest}\n")


def ensure_model(path: str, auto_download: bool = True) -> str:
    """Return a usable local path for a face model, downloading it if allowed.

    Raises ModelMissingError with actionable instructions rather than letting OpenCV
    fail later with an opaque message about parsing an empty ONNX graph.
    """
    filename = os.path.basename(path)
    if os.path.exists(path):
        if _looks_valid(path, filename):
            return path
        log.warning("%s exists but looks truncated or is a git-lfs pointer; refetching", path)
    if not auto_download:
        raise ModelMissingError(
            f"missing model: {path}\n"
            f"Download {filename} from https://github.com/opencv/opencv_zoo "
            f"(directory models/{MODEL_SOURCES.get(filename, ('?',))[0]}/) and save it to "
            f"that path, or call ensure_model(..., auto_download=True).")
    if filename not in MODEL_SOURCES:
        raise ModelMissingError(
            f"missing model: {path}\n"
            f"It is not one of the known downloadable models ({sorted(MODEL_SOURCES)}), "
            f"so it cannot be fetched automatically.")
    return download_model(filename, path)
