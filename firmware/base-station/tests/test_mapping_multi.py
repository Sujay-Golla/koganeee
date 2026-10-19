"""Camera isolation, failure handling and shared coordinates for the demo observer."""
import csv
from types import SimpleNamespace

import numpy as np
import pytest

from kogane_base.tools import mapping_multi as multi
from kogane_base.tools.mapping_demo import parser
from kogane_base.vision.detector import Track
from kogane_base.vision.geometry import FloorHomography, RoomProjector
from kogane_base.vision.sources import Frame


def test_baseline_centres_and_explicit_poses():
    args = parser().parse_args(["--camera", "1", "--camera2", "2"])
    assert np.allclose(multi.camera_poses(args), [(2.3, 0, 0), (2.7, 0, 0)])
    args.camera_x, args.camera2_yaw = 1.5, -15
    assert multi.camera_poses(args) == [(1.5, 0, 0), (1.9, 0, -15)]
    args.camera2 = 1
    with pytest.raises(ValueError, match="different camera indices"):
        multi.camera_poses(args)


def make_view(index, x=2):
    view = multi.CameraView(index, (x, 0, 0))
    view.detector = SimpleNamespace(track=lambda img: [Track(7, 200, 20, 400, 460, .9)])
    return view


def consume(view, now=10, sequence=1, frame=None, status="LIVE"):
    if frame is None and status == "LIVE":
        frame = Frame(np.zeros((480, 640, 3), np.uint8), sequence, now)
    return multi.consume(view, frame, sequence, status, now=now,
                         testing=False, hfov=70, height=1.7)


def test_camera_local_ids_project_separately_and_lock_independently(monkeypatch):
    monkeypatch.setattr(multi.time, "monotonic", lambda: 10)
    left, right = make_view(1, 1.8), make_view(2, 2.2)
    consume(left)
    consume(right)
    assert left.target.track_id == right.target.track_id == 7
    assert right.target.xy[0] - left.target.xy[0] == pytest.approx(.4)
    assert left.target is not right.target and left.target.kf is not right.target.kf
    left.locked_id = 999
    assert consume(left, sequence=2) is None  # no fallback to a different identity
    assert consume(right, sequence=2) is not None
    consume(left, sequence=2, status="camera disconnected")
    assert left.target.xy is None and left.frame is None
    assert right.target.fresh(10)


def test_dropped_and_slow_frames_never_refresh_a_target(monkeypatch):
    monkeypatch.setattr(multi.time, "monotonic", lambda: 10)
    view = make_view(0)
    assert consume(view) is not None
    assert consume(view, now=11, sequence=1) is None  # duplicate capture
    assert not view.target.fresh(11)
    stale = Frame(np.zeros((480, 640, 3), np.uint8), 2, 9)
    assert consume(view, now=11, sequence=2, frame=stale) is None
    assert view.tracks == []
    monkeypatch.setattr(multi.time, "monotonic", lambda: 12)
    assert consume(view, now=11, sequence=3) is None  # inference took too long
    assert not view.target.fresh(12)


def test_calibration_resolution_is_checked(monkeypatch):
    monkeypatch.setattr(multi.time, "monotonic", lambda: 10)
    view = make_view(1)
    view.projector = RoomProjector.from_homography(FloorHomography(np.eye(3), img_size=(1920, 1080)))
    view.calibrated = True
    with pytest.raises(ValueError, match="recalibrate"):
        consume(view)


def test_camera_test_skips_detection_and_marks_stale_view(monkeypatch):
    view = make_view(1)
    view.detector = None
    frame = Frame(np.zeros((480, 640, 3), np.uint8), 1, 10)
    assert multi.consume(view, frame, 1, "LIVE", now=10, testing=True, hfov=70, height=1.7) is None
    assert view.frame_live(10) and not view.frame_live(11)
    assert view.target.xy is None
    out = multi.render([view], now=11, room=(4, 5), testing=True)
    assert out.shape == (720, 1280, 3)


def test_headless_run_keeps_working_camera_and_finalizes_recording(tmp_path, monkeypatch):
    """One failed webcam must not stop its peer; CSV records camera-local provenance."""
    import time
    import cv2
    from kogane_base.vision import detector

    class Reader:
        instances = []

        def __init__(self, index, **kwargs):
            self.index, self.sequence, self.closed = index, 0, False
            self.instances.append(self)

        def start(self):
            pass

        def snapshot(self):
            self.sequence += 1
            if self.index == 2:
                return None, 0, "camera disconnected"
            return Frame(np.zeros((480, 640, 3), np.uint8), self.sequence, time.monotonic()), self.sequence, "LIVE"

        def close(self):
            self.closed = True

    monkeypatch.setattr(multi, "LatestCamera", Reader)
    monkeypatch.setattr(detector, "PersonDetector", lambda *a: make_view(0).detector)
    path = tmp_path / "dual.mp4"
    args = parser().parse_args(["--camera", "1", "--camera2", "2", "--headless",
                               "--seconds", ".15", "--record", str(path)])
    assert multi.run(args) == 2  # partial success is explicit
    assert all(reader.closed for reader in Reader.instances)
    with path.with_suffix(".csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows and {row["source"] for row in rows} == {"camera1"}
    assert {row["device"] for row in rows} == {"1"}
    cap = cv2.VideoCapture(str(path))
    try:
        assert cap.isOpened() and cap.read()[0]
    finally:
        cap.release()
