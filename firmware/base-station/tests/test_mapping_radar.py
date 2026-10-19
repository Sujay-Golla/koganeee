"""Radar position must not depend on camera visibility, IDs or stereo calibration."""
import csv
import math
from types import SimpleNamespace

import numpy as np
import pytest

from kogane_base.tools import mapping_radar
from kogane_base.tools.mapping_demo import parser
from kogane_base.tools.mapping_multi import CameraView
from kogane_base.tools.mapping_ui import presentation
from kogane_base.vision.sources import Frame


def test_single_radar_reports_drive_position_without_camera_data():
    tracker = mapping_radar.SingleRadarTrack((2.5, 0, 0))
    assert tracker.update([(2.5, 2)], 1, "", 0, 10)
    assert tracker.valid and tracker.distance_m == 2
    assert not tracker.update([(2.5, 2)], 1, "", .1, 10.1)
    assert tracker.target.updated == 10  # repeated snapshot cannot refresh position
    state = dict(target=tracker.target, valid=True, depth_m=tracker.distance_m,
                 status=tracker.status, position_source="radar")
    view = CameraView(2, (2.3, 0, 0), status="camera disconnected")
    assert presentation(state, [view], 10.1, (5, 4))["live"]
    assert not tracker.update([], 1, "", 1, 11)
    assert not tracker.valid and tracker.distance_m is None


def test_no_guessing_between_multiple_targets_or_during_radar_failure():
    tracker = mapping_radar.SingleRadarTrack((2.5, 0, 0))
    tracker.update([(2.5, 2)], 1, "", 0, 10)
    assert not tracker.update([(2.5, 2), (4, 3)], 2, "", 0, 10.1)
    assert not tracker.valid and tracker.status == "MULTIPLE RADAR TARGETS"
    assert not tracker.update([], 3, "", 0, 10.2)
    assert tracker.status == "NO RADAR TARGET"
    assert not tracker.update([(2.5, 2)], 4, "USB disconnected", 0, 10.3)
    assert tracker.status == "RADAR ERROR"
    assert not tracker.update([(math.nan, 2)], 4, "", 0, 10.3)


def test_large_position_jump_starts_a_new_path():
    tracker = mapping_radar.SingleRadarTrack((2.5, 0, 0))
    tracker.update([(2, 2)], 1, "", 0, 10)
    tracker.update([(2.1, 2)], 2, "", 0, 10.1)
    assert len(tracker.target.trail) == 2
    tracker.update([(4, 3)], 3, "", 0, 10.2)
    assert len(tracker.target.trail) == 1 and tracker.target.track_id == 2


def test_camera_detection_receives_the_entire_original_image():
    image = np.zeros((480, 640, 3), np.uint8)
    seen = []
    view = CameraView(2, (2.3, 0, 15))
    view.detector = SimpleNamespace(track=lambda pixels: seen.append(pixels) or [])
    assert mapping_radar.consume_camera(view, Frame(image, 1, 10), 1, "LIVE", 10)
    assert seen[0] is image and view.frame.image is image


@pytest.mark.parametrize("map_objects", [False, True])
def test_recorded_radar_mode_survives_camera_failure_without_calibration(tmp_path, monkeypatch, map_objects):
    import time
    from kogane_base.vision import detector

    class Reader:
        def __init__(self, index, **kwargs):
            self.index, self.sequence = index, 0

        def start(self):
            pass

        def snapshot(self):
            self.sequence += 1
            if self.index == 2:
                return None, 0, "camera disconnected"
            return Frame(np.zeros((480, 640, 3), np.uint8), self.sequence, time.monotonic()), self.sequence, "LIVE"

        def close(self):
            pass

    class Radar:
        def __init__(self, *args):
            self.n = 0

        def start(self):
            pass

        def snapshot(self, now):
            self.n += 1
            return [(2.5, 2)], self.n, "", 0

        def close(self):
            pass

    monkeypatch.setattr(mapping_radar, "LatestCamera", Reader)
    monkeypatch.setattr(mapping_radar, "RadarFeed", Radar)
    monkeypatch.setattr(detector, "PersonDetector", lambda *a: SimpleNamespace(track=lambda image: []))
    snapshots = []
    render = mapping_radar.render

    def capture(views, **kwargs):
        snapshots.append((views[0].status, kwargs["stereo"]["valid"]))
        return render(views, **kwargs)

    monkeypatch.setattr(mapping_radar, "render", capture)
    path = tmp_path / "radar.mp4"
    object_args = []
    if map_objects:
        from kogane_base.vision import objects
        from kogane_base.vision.geometry import FloorHomography
        hom_path = tmp_path / "right-floor.json"
        FloorHomography.from_points([(50, 450), (590, 450), (590, 100), (50, 100)],
                                    [(0, 0), (5, 0), (5, 4), (0, 4)], img_size=(640, 480)).save(str(hom_path))
        monkeypatch.setattr(objects, "SceneDetector", lambda *a: SimpleNamespace(
            track=lambda image: [], objects=[objects.ObjectTrack(9, 270, 160, 370, 300, .9)]))
        object_args = ["--map-objects", "--object-floor2", str(hom_path),
                       "--dashboard-width", "2560", "--record-width", "1920"]
    args = parser().parse_args(["--position-source", "radar", "--camera", "2", "--camera2", "1",
                               "--radar-port", "COM6", "--stereo-calibration", str(tmp_path/"absent.json"),
                               "--headless", "--seconds", ".2", "--record", str(path), *object_args])
    assert mapping_radar.run(args) == 0
    assert snapshots and all(error == "camera disconnected" and valid for error, valid in snapshots)
    with path.with_suffix(".csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows and {row["source"] for row in rows} == {"radar"}
    assert {row["distance_m"] for row in rows} == {"2.000"}
    if map_objects:
        import cv2
        capture = cv2.VideoCapture(str(path))
        try:
            ok, image = capture.read()
            assert ok and image.shape[:2] == (1080, 1920)
        finally:
            capture.release()
        with (tmp_path / "radar_objects.csv").open() as stream:
            object_rows = list(csv.DictReader(stream))
        assert object_rows and {row["source"] for row in object_rows} == {"camera_floor_anchor"}
        assert {row["camera"] for row in object_rows} == {"1"}
        assert {row["label"] for row in object_rows} == {"Chair"}
