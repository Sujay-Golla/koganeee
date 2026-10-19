"""Known geometry, real correspondence and missing-data checks for stereo depth."""
import numpy as np
import pytest

from kogane_base.vision.stereo import (PairSelector, RoomAlignment, StereoCalibration,
                                       StereoDepth, StereoError)
from kogane_base.vision.sources import Frame
from kogane_base.vision.detector import Track
from kogane_base.vision.stereo_calibrate import (board_html, corner_array, detect_board,
                                               draw_board, object_points, solve)


def calibration():
    k = np.array([[400, 0, 320], [0, 400, 240], [0, 0, 1]], float)
    return StereoCalibration(k, np.zeros(5), k.copy(), np.zeros(5), np.eye(3),
                             np.array([-.4, 0, 0]), (640, 480), (0, 1))


def frame(i, t):
    return Frame(np.zeros((2, 2, 3), np.uint8), i, t)


def test_pair_selector_uses_recent_distinct_frames_and_rejects_stale_skew():
    selector = PairSelector(.04)
    assert selector.select([frame(1, 10)], [frame(1, 10.1)], 10.2) is None
    pair = selector.select([frame(1, 10), frame(2, 10.2)], [frame(1, 10.01), frame(2, 10.21)], 10.22)
    assert pair[0].index == pair[1].index == 2
    assert selector.select([frame(2, 10.2)], [frame(3, 10.22)], 10.23) is None
    assert selector.select([frame(3, 10.24)], [frame(3, 10.25)], 11) is None
    assert selector.select([frame(4, 12)], [frame(4, 12)], 11) is None


def test_calibration_roundtrip_and_mismatch_refusal(tmp_path):
    cal = calibration()
    path = tmp_path / "stereo.json"
    cal.save(path)
    restored = StereoCalibration.load(path)
    assert restored.baseline_m == pytest.approx(.4)
    restored.validate_capture((0, 1), (640, 480), .4)
    for devices, size, baseline in [((1, 0), (640, 480), .4), ((0, 1), (1280, 720), .4), ((0, 1), (640, 480), .2)]:
        with pytest.raises(StereoError):
            restored.validate_capture(devices, size, baseline)
    with pytest.raises(StereoError, match="missing"):
        StereoCalibration.load(tmp_path / "absent.json")
    with pytest.raises(StereoError, match="quality"):
        cal.rms_px = 4
        cal.__post_init__()


def test_known_disparity_produces_one_metric_torso_fix_and_rejects_unsupported_data():
    depth = StereoDepth(calibration())
    disparity = np.full((480, 640), 40, np.float32)  # f*B/d = 400*.4/40 = 4m
    track = Track(7, 270, 100, 370, 420, .9)
    fix = depth.person_fix(disparity, track)
    assert fix is not None
    assert fix.xyz_left[2] == pytest.approx(4, abs=1e-5)
    assert abs(fix.xyz_left[0]) < .02
    assert fix.samples > 1000 and fix.valid_fraction == 1
    assert fix.right_box[0] < track.x1
    assert depth.person_fix(np.full_like(disparity, np.nan), track) is None
    assert depth.person_fix(np.full_like(disparity, 1), track) is None  # out of depth range
    assert depth.person_fix(disparity, Track(7, 2, 2, 5, 5, .9)) is None


def test_real_sgbm_matches_shifted_texture_and_rejects_unrelated_images():
    import cv2
    rng = np.random.default_rng(73)
    left = rng.integers(0, 256, (480, 640), dtype=np.uint8)
    left = cv2.GaussianBlur(left, (3, 3), .7)
    right = np.zeros_like(left)
    right[:, :-40] = left[:, 40:]
    depth = StereoDepth(calibration())
    images = [cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) for img in (left, right)]
    rectified = depth.rectify(*images)
    disparity = depth.disparity(*rectified)
    fix = depth.person_fix(disparity, Track(1, 260, 70, 400, 440, .9))
    assert fix is not None and fix.xyz_left[2] == pytest.approx(4, abs=.03)
    unrelated = cv2.cvtColor(rng.integers(0, 256, left.shape, dtype=np.uint8), cv2.COLOR_GRAY2BGR)
    assert depth.person_fix(depth.disparity(images[0], unrelated), Track(1, 260, 70, 400, 440, .9)) is None


def test_floor_alignment_accounts_for_camera_height_and_tilt(tmp_path):
    import cv2
    from kogane_base.vision.geometry import FloorHomography
    cal = calibration()
    rotation = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)
    centre = np.array([2.3, 0, 1.4])
    translation = -rotation @ centre
    world = np.array([[1.7, 2, 0], [3, 2, 0], [3, 3.5, 0], [1.7, 3.5, 0]], float)
    rv, _ = cv2.Rodrigues(rotation)
    pixels, _ = cv2.projectPoints(world, rv, translation, cal.K1, cal.D1)
    hom = FloorHomography.from_points(pixels.reshape(-1, 2), world[:, :2], img_size=cal.size)
    path = tmp_path / "floor.json"
    hom.save(str(path))
    alignment = RoomAlignment.from_floor(path, cal)
    target_room = np.array([2.5, 2, 1.2])
    xyz_left = rotation @ target_room+translation
    assert alignment.to_room(xyz_left) == pytest.approx(target_room, abs=1e-5)


def test_calibration_recovers_known_camera_spacing_from_many_board_poses():
    import cv2
    cal = calibration()
    rng = np.random.default_rng(9)
    samples = []
    obj = object_points(.025)
    for i in range(24):
        rv = rng.uniform(-.45, .45, 3)
        tv = np.array([rng.uniform(-.18, .15), rng.uniform(-.16, .14), rng.uniform(.75, 1.5)])
        a, _ = cv2.projectPoints(obj, rv, tv, cal.K1, cal.D1)
        b, _ = cv2.projectPoints(obj, rv, tv+cal.T.reshape(3), cal.K2, cal.D2)
        samples.append((a, b))
    result = solve(samples, size=cal.size, devices=cal.devices, square_m=.025, expected_baseline=.4)
    assert result.baseline_m == pytest.approx(.4, abs=.002)
    assert result.rms_px < .05 and result.epipolar_px < .05
    with pytest.raises(StereoError, match="18"):
        solve(samples[:5], size=cal.size, devices=cal.devices, square_m=.025, expected_baseline=.4)


def test_tablet_board_is_only_generated_content():
    html = board_html()
    assert "9 x 6 INNER corners" in html
    assert html.count('fill="black"') == 35
    assert "<script src" not in html and "fetch(" not in html  # no remote dependencies


@pytest.mark.parametrize("shape", [(54, 2), (54, 1, 2)])
def test_checkerboard_point_shapes_work_for_overlay_and_capture(shape):
    points = np.mgrid[1:10, 1:7].T.reshape(-1, 2).astype(np.float32)*30
    normalized = corner_array(points.reshape(shape))
    assert normalized.shape == (54, 1, 2) and normalized.dtype == np.float32
    image = np.zeros((240, 330, 3), np.uint8)
    draw_board(image, points.reshape(shape))  # includes the origin marker that crashed
    assert image.any()
    direction = normalized[8, 0]-normalized[0, 0]
    assert direction.shape == (2,)
    saved_sample = normalized.tolist()
    assert np.linalg.norm(normalized-np.asarray(saved_sample), axis=2).max() == 0


def test_installed_checkerboard_detector_feeds_overlay_without_shape_error():
    import cv2
    # Exercise real detector output, not only projected corners from calibration math.
    board = np.full((360, 480, 3), 255, np.uint8)
    for row in range(7):
        for col in range(10):
            if (row+col) % 2 == 0:
                board[40+row*40:40+(row+1)*40, 40+col*40:40+(col+1)*40] = 0
    corners = detect_board(board)
    assert corners is not None and corners.shape == (54, 1, 2)
    draw_board(board, corners)
    assert detect_board(np.full_like(board, 255)) is None


def test_stereo_runner_outputs_one_identity_and_hides_depth_when_camera_lost(tmp_path, monkeypatch):
    import cv2
    import time
    from kogane_base.tools import mapping_stereo
    from kogane_base.tools.mapping_demo import parser
    from kogane_base.vision import detector
    rng = np.random.default_rng(8)
    left = cv2.GaussianBlur(rng.integers(0, 256, (480, 640), dtype=np.uint8), (3, 3), .7)
    right = np.zeros_like(left)
    right[:, :-40] = left[:, 40:]
    images = [cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) for img in (left, right)]

    class Reader:
        def __init__(self, index, **kwargs):
            self.index, self.i, self.closed = index, 0, False

        def start(self):
            pass

        def history(self):
            self.i += 1
            if self.index == 1 and self.i > 2:
                return [], "camera disconnected"
            return [Frame(images[self.index], self.i, time.monotonic())], "LIVE"

        def close(self):
            self.closed = True

    monkeypatch.setattr(mapping_stereo, "LatestCamera", Reader)
    person = Track(7, 260, 70, 400, 440, .9)
    monkeypatch.setattr(detector, "PersonDetector", lambda *a: type("Detector", (), {"track": lambda self, img: [person]})())
    states = []
    original_render = mapping_stereo.render

    def record_state(views, **kwargs):
        states.append((kwargs["stereo"]["valid"], [t.track_id for v in views for t in v.tracks]))
        return original_render(views, **kwargs)

    monkeypatch.setattr(mapping_stereo, "render", record_state)
    cal_path = tmp_path / "cal.json"
    calibration().save(cal_path)
    path = tmp_path / "single_person.mp4"
    args = parser().parse_args(["--camera", "0", "--camera2", "1", "--stereo-calibration", str(cal_path),
                               "--headless", "--seconds", ".3", "--record", str(path)])
    assert mapping_stereo.run(args) == 0
    assert any(valid and ids == [7, 7] for valid, ids in states)  # two views of ONE identity
    assert states[-1][0] is False  # camera loss removes current stereo position
    import csv
    with path.with_suffix(".csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows and {row["source"] for row in rows} == {"stereo"}
    assert {row["track_id"] for row in rows} == {"7"}


def test_second_camera_defaults_to_stereo_and_uses_five_metre_wall(monkeypatch):
    from kogane_base.tools import mapping_demo, mapping_stereo
    calls = []
    monkeypatch.setattr(mapping_stereo, "run", lambda args: calls.append(args) or 0)
    assert mapping_demo.main(["--camera", "0", "--camera2", "1"]) == 0
    assert calls[0].room_width == 5 and calls[0].room_depth == 4


def test_limited_coverage_uses_heldout_validation_and_retains_quality_limits(tmp_path):
    import cv2
    cal = calibration()
    rng = np.random.default_rng(38)
    obj = object_points(.018)
    samples = []
    for _ in range(24):
        rv = rng.uniform(-.4, .4, 3)
        tv = np.array([rng.uniform(.08, .10), rng.uniform(-.15, .13), rng.uniform(.8, 1.4)])
        left, _ = cv2.projectPoints(obj, rv, tv, cal.K1, cal.D1)
        right, _ = cv2.projectPoints(obj, rv, tv+cal.T.reshape(3), cal.K2, cal.D2)
        samples.append((left, right))
    kwargs = dict(size=cal.size, devices=cal.devices, square_m=.018, expected_baseline=.4)
    with pytest.raises(StereoError, match="coverage"):
        solve(samples, **kwargs)
    report = {}
    result = solve(samples, allow_limited_coverage=True, report=report, **kwargs)
    assert result.quality_notes and len(report["held_out"]) == 3
    assert result.baseline_m == pytest.approx(.4, abs=.002)
    path = tmp_path / "limited.json"
    result.save(path)
    assert StereoCalibration.load(path).quality_notes == result.quality_notes
    corrupted = [(a, b+rng.normal(0, 8, b.shape).astype(np.float32)) for a, b in samples]
    with pytest.raises(StereoError, match="quality"):
        solve(corrupted, allow_limited_coverage=True, **kwargs)


def test_disparity_range_adapts_to_real_narrow_lenses():
    cal = calibration()
    cal.K1[0, 0] = cal.K1[1, 1] = 1200
    cal.K2[0, 0] = cal.K2[1, 1] = 1200
    depth = StereoDepth(cal)
    assert depth.num_disparities == 304
    assert depth.nominal_near_m == pytest.approx(1200*.4/304)


def test_interactive_capture_saves_unmarked_images_and_corner_coordinates(tmp_path, monkeypatch):
    import cv2
    import json
    import time
    from kogane_base.vision import stereo_calibrate
    from kogane_base.tools import mapping_multi
    images = {2: np.full((480, 640, 3), 40, np.uint8), 1: np.full((480, 640, 3), 80, np.uint8)}

    class Reader:
        def __init__(self, index, **kwargs):
            self.index, self.sequence = index, 0

        def start(self):
            pass

        def history(self):
            self.sequence += 1
            return [Frame(images[self.index], self.sequence, time.monotonic())], "LIVE"

        def close(self):
            pass

    points = np.mgrid[1:10, 1:7].T.reshape(-1, 1, 2).astype(np.float32)*30
    monkeypatch.setattr(mapping_multi, "LatestCamera", Reader)
    monkeypatch.setattr(stereo_calibrate, "detect_board", lambda image: points.copy())
    monkeypatch.setattr(cv2, "imshow", lambda *a: None)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    keys = iter((ord("s"), ord("q")))
    monkeypatch.setattr(cv2, "waitKey", lambda *a: next(keys))
    path = tmp_path / "corners.json"
    assert stereo_calibrate.main(["--camera", "2", "--camera2", "1", "--square-mm", "18",
                                  "--samples", str(path), "--image-dir", str(tmp_path/"images")]) == 0
    saved = json.loads(path.read_text())
    assert len(saved["samples"]) == len(saved["image_pairs"]) == 1
    assert saved["devices"] == [2, 1] and saved["square_mm"] == 18
    for index, filename in zip((2, 1), saved["image_pairs"][0]):
        assert np.array_equal(cv2.imread(filename), images[index])
