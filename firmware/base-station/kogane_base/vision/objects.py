"""Furniture detection and approximate floor anchors for fixed room cameras.

Anchors are box-bottom projections, not measured obstacle footprints or heights.
The floor-contact assumption must be checked by the operator. No flight output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from .detector import PersonDetector, Track
from .geometry import FloorHomography, FloorHomographyError


# Floor-standing COCO classes only. Objects on shelves/tables violate this method.
FLOOR_CLASSES = {13: "Bench", 28: "Suitcase", 56: "Chair", 57: "Sofa",
                 58: "Plant", 59: "Bed", 60: "Table"}


@dataclass
class ObjectTrack(Track):
    class_id: int = 56

    @property
    def label(self):
        return FLOOR_CLASSES[self.class_id]


class SceneDetector(PersonDetector):
    """One model/inference per image, with separate person and furniture results."""

    def __init__(self, model_path="yolov8n.pt"):
        super().__init__(model_path)
        self.objects = []

    def track(self, image):
        self.objects = []
        people = []
        results = self.model.track(image, persist=True, classes=[0, *FLOOR_CLASSES],
                                   conf=self.conf, tracker=self.tracker,
                                   device=self.device, verbose=False)
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                class_id = int(box.cls[0])
                coords = tuple(float(v) for v in box.xyxy[0].tolist())
                track_id = int(box.id[0]) if box.id is not None else -1
                args = (track_id, *coords, float(box.conf[0]))
                if class_id == 0:
                    people.append(Track(*args))
                elif class_id in FLOOR_CLASSES:
                    self.objects.append(ObjectTrack(*args, class_id=class_id))
        return people


def load_floor(path):
    """Require the capture geometry and measured calibration region to be known."""
    import cv2
    hom = FloorHomography.load(str(path))
    pts = np.asarray(hom.image_pts, dtype=np.float32)
    if (hom.img_size is None or len(hom.img_size) != 2 or min(hom.img_size) <= 0 or
            pts.ndim != 2 or pts.shape[1:] != (2,) or len(pts) < 4 or
            not np.isfinite(pts).all() or cv2.contourArea(cv2.convexHull(pts)) < 100):
        raise ValueError(f"{path}: recapture 4+ spread-out floor points with the webcam calibration tool; image size and points are required")
    return hom


@dataclass
class MappedObject:
    identity: int
    class_id: int
    xy: tuple
    last_seen: float
    sources: dict = field(default_factory=dict)  # camera -> (last image time, local id)
    hits: int = 1


class ObjectMapper:
    """Short-lived, conservative spatial association of floor-standing objects.

    Every observation is consumed once. A second camera may join an existing
    anchor only when it is the unique nearby candidate of the same class.
    """

    def __init__(self, room, floors=None, memory_s=12):
        self.room, self.floors = room, floors or {}
        self.memory_s = memory_s
        self.items = []
        self.processed = {}
        self.status = {}
        self.next_id = 1

    def clear(self):
        self.items.clear()

    def observe_views(self, views, now):
        import cv2
        observations = []
        self.items = [item for item in self.items if 0 <= now-item.last_seen <= self.memory_s]
        for view in views:
            hom = self.floors.get(view.index)
            if hom is None:
                self.status[view.index] = "Floor calibration needed"
                continue
            if not view.frame_live(now):
                self.status[view.index] = "Waiting for video"
                continue
            h, w = view.frame.image.shape[:2]
            if (w, h) != hom.img_size:
                self.status[view.index] = f"Recalibrate at {w}×{h}"
                continue
            self.status[view.index] = "Floor anchors approximate"
            if self.processed.get(view.index) == view.processed:
                continue
            self.processed[view.index] = view.processed
            hull = cv2.convexHull(np.asarray(hom.image_pts, np.float32))
            used = set()
            for obj in getattr(view, "objects", []):
                values = (obj.x1, obj.y1, obj.x2, obj.y2, obj.conf)
                if (obj.class_id not in FLOOR_CLASSES or not all(math.isfinite(v) for v in values)
                        or obj.conf < .5 or obj.x1 < 3 or obj.x2 > w-3 or obj.y2 > h-3
                        or obj.y1 < 0 or obj.x2 <= obj.x1 or obj.y2 <= obj.y1):
                    continue
                if cv2.pointPolygonTest(hull, obj.foot, False) < 0:
                    continue  # no extrapolation beyond measured floor region
                u, v = obj.foot
                if any(person.x1-6 <= u <= person.x2+6 and person.y1 <= v <= person.y2+4
                       for person in view.tracks):
                    continue  # person obscures the estimated floor contact
                try:
                    xy = hom.image_to_room(*obj.foot)
                except (FloorHomographyError, ValueError, OverflowError):
                    continue
                if not all(math.isfinite(v) and 0 <= v <= limit for v, limit in zip(xy, self.room)):
                    continue
                timestamp = view.frame.t_mono
                candidates = [item for item in self.items if item.class_id == obj.class_id
                              and item.identity not in used and math.dist(item.xy, xy) <= .35]
                # Prefer a recent same-camera ID; never let it jump across the room.
                same = [item for item in candidates if obj.track_id >= 0 and
                        item.sources.get(view.index, (None, None))[1] == obj.track_id]
                if len(same) == 1:
                    match = same[0]
                elif len(candidates) == 1 and (
                        view.index not in candidates[0].sources or
                        (obj.track_id < 0 and candidates[0].sources[view.index][1] < 0) or
                        timestamp-candidates[0].sources[view.index][0] > 1):
                    match = candidates[0]
                else:
                    match = None
                if match is None:
                    match = MappedObject(self.next_id, obj.class_id, xy, timestamp)
                    self.next_id += 1
                    self.items.append(match)
                else:
                    # Bounded smoothing of approximate anchors, not object dimensions.
                    match.xy = tuple(.65*a+.35*b for a, b in zip(match.xy, xy))
                    match.last_seen = max(match.last_seen, timestamp)
                    match.hits += 1
                match.sources[view.index] = (timestamp, obj.track_id)
                used.add(match.identity)
                observations.append(dict(identity=match.identity, label=obj.label, xy=xy,
                                         camera=view.index, timestamp=timestamp, confidence=obj.conf))
        return observations

    def snapshot(self, now):
        return [dict(identity=item.identity, label=FLOOR_CLASSES[item.class_id], xy=item.xy,
                     age_s=max(0, now-item.last_seen), visible=now-item.last_seen <= 1,
                     cameras=sorted(cam for cam, (t, _) in item.sources.items() if now-t <= 1))
                for item in self.items if item.hits >= 2 and 0 <= now-item.last_seen <= self.memory_s]
