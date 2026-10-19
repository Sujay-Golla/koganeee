"""Exercise projected objects, overlap, occlusion and memory without real hardware."""
from types import SimpleNamespace

import numpy as np
import pytest

from kogane_base.tools.mapping_multi import CameraView
from kogane_base.tools.mapping_radar import consume_camera
from kogane_base.vision.detector import Track
from kogane_base.vision.geometry import FloorHomography
from kogane_base.vision.objects import ObjectMapper, ObjectTrack, SceneDetector, load_floor
from kogane_base.vision.sources import Frame


def floor():
    return FloorHomography.from_points([(50, 450), (590, 450), (590, 100), (50, 100)],
                                       [(0, 0), (5, 0), (5, 4), (0, 4)], img_size=(640, 480))


def view(index=2, t=10, seq=1, objects=None):
    camera = CameraView(index, (2.5, 0, 0), status="LIVE", processed=seq)
    camera.frame = Frame(np.zeros((480, 640, 3), np.uint8), seq, t)
    camera.objects = [ObjectTrack(8, 270, 160, 370, 300, .9)] if objects is None else objects
    return camera


def advance(camera, t=10.1):
    camera.processed += 1
    camera.frame = Frame(camera.frame.image, camera.processed, t)


def test_anchor_uses_floor_contact_and_old_frames_never_refresh_memory():
    mapper, camera = ObjectMapper((5, 4), {2: floor()}), view()
    mapper.observe_views([camera], 10)
    assert not mapper.snapshot(10)  # needs repeat support
    advance(camera)
    observations = mapper.observe_views([camera], 10.1)
    anchor = mapper.snapshot(10.1)[0]
    assert anchor["xy"] == pytest.approx(floor().image_to_room(320, 300))
    assert anchor["visible"] and anchor["label"] == "Chair"
    assert observations[0]["timestamp"] == 10.1
    assert mapper.observe_views([camera], 10.4) == []
    held = mapper.snapshot(12)[0]
    assert not held["visible"] and held["age_s"] == pytest.approx(1.9)
    assert mapper.snapshot(23) == []


def test_one_object_in_two_cameras_joins_but_two_nearby_objects_in_one_view_do_not():
    mapper = ObjectMapper((5, 4), {1: floor(), 2: floor()})
    a, b = view(), view(1)
    mapper.observe_views([a, b], 10)
    anchor = mapper.snapshot(10)[0]
    assert anchor["cameras"] == [1, 2] and len(mapper.items) == 1
    mapper = ObjectMapper((5, 4), {2: floor()})
    a.objects.append(ObjectTrack(9, 290, 160, 390, 300, .9))
    mapper.observe_views([a], 10)
    advance(a)
    mapper.observe_views([a], 10.1)
    assert len(mapper.snapshot(10.1)) == 2


@pytest.mark.parametrize("case", ["uncalibrated", "size", "outside", "clipped", "weak", "person", "stale"])
def test_missing_geometry_or_unreliable_floor_contact_never_makes_a_map_point(case):
    camera = view()
    mapper = ObjectMapper((5, 4), {2: floor()} if case != "uncalibrated" else {})
    if case == "size":
        camera.frame = Frame(np.zeros((720, 1280, 3), np.uint8), 1, 10)
    elif case == "outside":
        camera.objects[0].y2 = 470
    elif case == "clipped":
        camera.objects[0].x1 = 0
    elif case == "weak":
        camera.objects[0].conf = .3
    elif case == "person":
        camera.tracks = [Track(1, 290, 120, 350, 430, .9)]
    now = 12 if case == "stale" else 10
    assert mapper.observe_views([camera], now) == []
    assert not mapper.items


def test_disconnect_keeps_only_explicit_last_seen_and_clear_removes_it():
    camera, mapper = view(), ObjectMapper((5, 4), {2: floor()})
    mapper.observe_views([camera], 10)
    advance(camera)
    mapper.observe_views([camera], 10.1)
    camera.status = "disconnected"
    assert mapper.observe_views([camera], 12) == []
    assert not mapper.snapshot(12)[0]["visible"]
    mapper.clear()
    assert not mapper.snapshot(12)


def test_calibration_requires_capture_size_and_floor_region(tmp_path):
    path = tmp_path / "floor.json"
    floor().save(str(path))
    assert load_floor(path).img_size == (640, 480)
    FloorHomography(np.eye(3)).save(str(path))
    with pytest.raises(ValueError, match="spread-out floor points"):
        load_floor(path)


def test_scene_model_runs_once_and_separates_people_from_furniture():
    def box(class_id, track_id):
        return SimpleNamespace(cls=[class_id], id=[track_id], conf=[.9],
                               xyxy=np.array([[50, 60, 160, 300]]))
    calls = []
    scene = SceneDetector.__new__(SceneDetector)
    scene.conf, scene.tracker, scene.device = .35, "bytetrack.yaml", "cpu"
    scene.model = SimpleNamespace(track=lambda image, **kw: calls.append(kw) or
                                  [SimpleNamespace(boxes=[box(0, 1), box(56, 2)])])
    people = scene.track(np.zeros((480, 640, 3), np.uint8))
    assert len(calls) == 1 and {0, 56, 60} <= set(calls[0]["classes"])
    assert [p.track_id for p in people] == [1]
    assert scene.objects[0].label == "Chair"
    camera = view()
    camera.detector = scene
    assert consume_camera(camera, camera.frame, 2, "LIVE", 10)
    assert len(camera.tracks) == 1 and len(camera.objects) == 1
    consume_camera(camera, None, 0, "disconnected", 11)
    assert not camera.objects
