"""YOLOv8n person detector with built-in multi-object tracking.

Uses ultralytics' `model.track(persist=True)` (ByteTrack) so each person keeps a
stable `track_id` across frames — that id is what lets us "lock on" to the user.
Only COCO class 0 (person) is kept.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Track:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def foot(self) -> tuple[float, float]:
        """Bottom-center point — where the person meets the floor (for ground projection)."""
        return (self.x1 + self.x2) / 2.0, self.y2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height


class PersonDetector:
    PERSON_CLASS = 0  # COCO

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu",
                 conf: float = 0.35, tracker: str = "bytetrack.yaml") -> None:
        from ultralytics import YOLO  # local import; only needed when CV is used

        self.model = YOLO(model_path)
        self.device = device
        self.conf = conf
        self.tracker = tracker

    def track(self, image) -> list[Track]:
        results = self.model.track(
            image,
            persist=True,
            classes=[self.PERSON_CLASS],
            conf=self.conf,
            tracker=self.tracker,
            device=self.device,
            verbose=False,
        )
        out: list[Track] = []
        if not results:
            return out
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            # detections without ids (e.g. very first frame) -> still report with id -1
            if r.boxes is not None:
                for b in r.boxes:
                    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
                    out.append(Track(-1, x1, y1, x2, y2, float(b.conf[0])))
            return out
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
            tid = int(b.id[0]) if b.id is not None else -1
            out.append(Track(tid, x1, y1, x2, y2, float(b.conf[0])))
        return out


def select_primary(tracks: list[Track], locked_id: int | None = None) -> Track | None:
    """Choose the person to follow.

    If `locked_id` is set and present, follow it; otherwise pick the largest box
    (a reasonable 'closest person' heuristic). Face-ID can later override this.
    """
    if not tracks:
        return None
    if locked_id is not None:
        for t in tracks:
            if t.track_id == locked_id:
                return t
    return max(tracks, key=lambda t: t.area)
