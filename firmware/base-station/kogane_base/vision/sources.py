"""Pluggable video frame sources, all via OpenCV VideoCapture.

    webcam      -> integer camera index (default 0)
    video file  -> a path to a .mp4/.mov/etc.
    mjpeg       -> the drone ESP32-CAM/OV2640 stream URL (http://<ip>/stream)

The same detector runs regardless of source, so you can develop on the laptop
webcam today and point at the drone camera later with only a flag change.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Frame:
    image: "any"        # np.ndarray (H, W, 3) BGR
    index: int
    t_mono: float


class FrameSource:
    """Thin wrapper over cv2.VideoCapture with an iterator interface."""

    def __init__(self, spec: "int | str", api_pref: int | None = None) -> None:
        import cv2  # local import so the base package works without the vision extra

        self._cv2 = cv2
        if api_pref is None:
            self.cap = cv2.VideoCapture(spec)
        else:
            self.cap = cv2.VideoCapture(spec, api_pref)
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open video source: {spec!r}")
        self._i = 0

    @property
    def size(self) -> tuple[int, int]:
        w = int(self.cap.get(self._cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(self._cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    def __iter__(self):
        return self

    def __next__(self) -> Frame:
        ok, img = self.cap.read()
        if not ok:
            raise StopIteration
        f = Frame(image=img, index=self._i, t_mono=time.monotonic())
        self._i += 1
        return f

    def release(self) -> None:
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def make_source(kind: str, value: str | None) -> FrameSource:
    """Factory used by the demo CLI.

    kind: 'webcam' | 'video' | 'mjpeg' | 'usb'
    """
    if kind in ("webcam", "usb"):
        idx = int(value) if value not in (None, "") else 0
        return FrameSource(idx)
    if kind == "video":
        if not value:
            raise ValueError("video source requires a file path")
        return FrameSource(value)
    if kind == "mjpeg":
        if not value:
            raise ValueError("mjpeg source requires a stream URL")
        return FrameSource(value)
    raise ValueError(f"unknown source kind: {kind}")
