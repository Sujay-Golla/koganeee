"""Floor homography: round-trip accuracy, persistence, and failure modes.

Synthetic points only — no camera, no calibration rig. The homography is exercised for
real (cv2.findHomography actually runs); what is synthetic is the point correspondence.
"""
from __future__ import annotations

import math

import pytest

from kogane_base.vision.geometry import (CameraEstimate, FloorHomography,
                                         FloorHomographyError, MonocularEstimator,
                                         RoomProjector, project_to_room)


class FakeTrack:
    """Minimal stand-in for detector.Track: just needs the box and .foot/.conf."""

    def __init__(self, x1, y1, x2, y2, conf=0.9):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.conf = conf

    @property
    def foot(self):
        return ((self.x1 + self.x2) / 2.0, self.y2)


# A plausible downward-looking camera view of a 3 m x 4 m floor rectangle: the far edge
# is narrower in the image than the near edge, which is what makes this a real
# perspective transform rather than an affine one.
IMAGE_PTS = [(120.0, 460.0), (520.0, 460.0), (430.0, 250.0), (210.0, 250.0)]
ROOM_PTS = [(0.0, 0.0), (3.0, 0.0), (3.0, 4.0), (0.0, 4.0)]


def make_hom() -> FloorHomography:
    return FloorHomography.from_points(IMAGE_PTS, ROOM_PTS, img_size=(640, 480),
                                       note="synthetic test rig")


def test_calibration_points_round_trip_exactly():
    hom = make_hom()
    for (u, v), (x, y) in zip(IMAGE_PTS, ROOM_PTS):
        px, py = hom.image_to_room(u, v)
        assert px == pytest.approx(x, abs=1e-6)
        assert py == pytest.approx(y, abs=1e-6)
    assert hom.reprojection_error_m() == pytest.approx(0.0, abs=1e-6)


def test_image_room_inverse_round_trip():
    """room -> image -> room must return the original point, including off-grid ones."""
    hom = make_hom()
    for x, y in [(1.5, 2.0), (0.25, 0.25), (2.75, 3.5), (1.0, 1.0)]:
        u, v = hom.room_to_image(x, y)
        bx, by = hom.image_to_room(u, v)
        assert bx == pytest.approx(x, abs=1e-6)
        assert by == pytest.approx(y, abs=1e-6)


def test_interior_point_maps_inside_the_rectangle():
    hom = make_hom()
    # centre of the imaged quad should land inside the room rectangle
    cu = sum(p[0] for p in IMAGE_PTS) / 4.0
    cv_ = sum(p[1] for p in IMAGE_PTS) / 4.0
    x, y = hom.image_to_room(cu, cv_)
    assert 0.0 < x < 3.0
    assert 0.0 < y < 4.0


def test_perspective_is_not_affine():
    """Sanity: a midpoint in the image is NOT the midpoint in the room.

    If this ever passed as an equality it would mean we fitted a degenerate transform
    and the whole point of using a homography would be lost.
    """
    hom = make_hom()
    near_mid = hom.image_to_room((IMAGE_PTS[0][0] + IMAGE_PTS[3][0]) / 2,
                                 (IMAGE_PTS[0][1] + IMAGE_PTS[3][1]) / 2)
    assert near_mid[1] != pytest.approx(2.0, abs=0.05)


def test_track_foot_is_what_gets_projected():
    hom = make_hom()
    # a box whose bottom-centre sits exactly on a calibration point
    t = FakeTrack(x1=70.0, y1=200.0, x2=170.0, y2=460.0)
    fix = hom.track_to_room(t)
    direct = hom.image_to_room(120.0, 460.0)
    assert (fix.x_m, fix.y_m) == pytest.approx(direct)
    assert fix.conf == pytest.approx(0.9)


def test_more_than_four_points_uses_ransac_and_still_fits():
    extra_img = IMAGE_PTS + [(320.0, 350.0), (250.0, 300.0)]
    extra_room = ROOM_PTS + [(1.5, 1.74), (0.6, 2.9)]
    hom = FloorHomography.from_points(extra_img, extra_room)
    # not exact any more (the extra points are approximate), but it must stay sane
    assert hom.reprojection_error_m() < 0.6


def test_save_load_round_trip(tmp_path):
    hom = make_hom()
    path = tmp_path / "nested" / "floor.json"
    hom.save(str(path))
    assert path.exists()

    back = FloorHomography.load(str(path))
    for (u, v) in IMAGE_PTS:
        assert back.image_to_room(u, v) == pytest.approx(hom.image_to_room(u, v), abs=1e-9)
    assert back.img_size == (640, 480)
    assert back.note == "synthetic test rig"
    assert back.reprojection_error_m() == pytest.approx(0.0, abs=1e-6)


def test_missing_calibration_file_message_is_actionable(tmp_path):
    with pytest.raises(FloorHomographyError) as ei:
        FloorHomography.load(str(tmp_path / "nope.json"))
    msg = str(ei.value)
    assert "no floor calibration" in msg
    assert "calibrate" in msg          # points the user at the tool


def test_corrupt_calibration_file_raises_cleanly(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(FloorHomographyError):
        FloorHomography.load(str(p))

    p2 = tmp_path / "nokey.json"
    p2.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(FloorHomographyError):
        FloorHomography.load(str(p2))


def test_too_few_points_rejected():
    with pytest.raises(FloorHomographyError, match="at least 4"):
        FloorHomography.from_points(IMAGE_PTS[:3], ROOM_PTS[:3])


def test_point_count_mismatch_rejected():
    with pytest.raises(FloorHomographyError, match="mismatch"):
        FloorHomography.from_points(IMAGE_PTS, ROOM_PTS[:3])


def test_collinear_points_rejected():
    collinear = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
    with pytest.raises(FloorHomographyError):
        FloorHomography.from_points(collinear, ROOM_PTS)


def test_bad_matrix_shape_rejected():
    with pytest.raises(FloorHomographyError, match="3x3"):
        FloorHomography([[1, 0], [0, 1]])


def test_singular_matrix_rejected():
    with pytest.raises(FloorHomographyError, match="singular"):
        FloorHomography([[1, 2, 3], [2, 4, 6], [1, 1, 1]])


# ---- MonocularEstimator stays intact as the drone-camera path ----

def test_monocular_centre_box_has_zero_bearing():
    est = MonocularEstimator(640, 480, hfov_deg=70.0, assumed_person_height_m=1.7)
    e = est.estimate(300.0, 100.0, 340.0, 400.0)
    assert e.bearing_deg == pytest.approx(0.0, abs=1e-6)
    assert e.x_m == pytest.approx(0.0, abs=1e-9)
    assert e.y_m == pytest.approx(e.distance_m, abs=1e-9)


def test_monocular_bigger_box_means_closer():
    est = MonocularEstimator(640, 480)
    near = est.estimate(280, 40, 360, 440)     # tall box
    far = est.estimate(300, 200, 340, 300)     # short box
    assert near.distance_m < far.distance_m


def test_monocular_bearing_sign_is_right_positive():
    est = MonocularEstimator(640, 480)
    right = est.estimate(500, 100, 560, 400)
    left = est.estimate(80, 100, 140, 400)
    assert right.bearing_deg > 0
    assert left.bearing_deg < 0


def test_project_to_room_matches_mmwave_convention():
    """Pins the rotation convention shared with tracking.mmwave.node_frame_to_room.

    Sensor frame is +x right, +y forward; yaw rotates it into the room frame as
    (x*cos - y*sin, x*sin + y*cos). So yaw=0 => camera looks along room +y.
    """
    straight_ahead = CameraEstimate(0.0, 2.0, 0.0, 2.0, 1.0)

    # yaw 0, camera at (1, 1): 2 m forward lands 2 m along room +y
    assert project_to_room(straight_ahead, (1.0, 1.0, 0.0)) == pytest.approx((1.0, 3.0),
                                                                            abs=1e-9)
    # yaw 90 turns forward onto room -x
    assert project_to_room(straight_ahead, (1.0, 1.0, 90.0)) == pytest.approx((-1.0, 1.0),
                                                                             abs=1e-9)
    # yaw -90 turns forward onto room +x
    assert project_to_room(straight_ahead, (1.0, 1.0, -90.0)) == pytest.approx((3.0, 1.0),
                                                                              abs=1e-9)


def test_project_to_room_is_the_same_formula_as_the_mmwave_nodes():
    """Belt-and-braces: identical inputs must give identical outputs to the mmWave path."""
    from kogane_base.config import CONFIG
    from kogane_base.tracking.mmwave import node_frame_to_room

    pose = CONFIG.node_poses[0]
    est = CameraEstimate(0.0, 0.0, 1.2, 3.4, 1.0)   # x=1.2 m right, y=3.4 m forward
    cam = project_to_room(est, pose)
    node = node_frame_to_room(0, 1200, 3400)         # same point, in mm
    assert cam == pytest.approx(node, abs=1e-9)


def test_lateral_offset_rotates_correctly():
    """A purely lateral estimate must rotate too, not just the forward component."""
    lateral = CameraEstimate(90.0, 1.0, 1.0, 0.0, 1.0)   # 1 m to the camera's right
    assert project_to_room(lateral, (0.0, 0.0, 0.0)) == pytest.approx((1.0, 0.0), abs=1e-9)
    assert project_to_room(lateral, (0.0, 0.0, 90.0)) == pytest.approx((0.0, 1.0), abs=1e-9)


# ---- RoomProjector: the explicit method choice ----

def test_projector_reports_which_method_is_live():
    hom = make_hom()
    assert RoomProjector.from_homography(hom).method == "homography"
    mono = RoomProjector.from_monocular(MonocularEstimator(640, 480), (0.0, 0.0, 90.0))
    assert mono.method == "monocular"


def test_projector_homography_output_is_not_double_transformed():
    """Homography output is already room-frame; it must not also go through cam_pose."""
    hom = make_hom()
    proj = RoomProjector.from_homography(hom)
    t = FakeTrack(70.0, 200.0, 170.0, 460.0)
    fix = proj.locate(t)
    assert (fix.x_m, fix.y_m) == pytest.approx(hom.image_to_room(120.0, 460.0))
    assert fix.distance_m is None      # homography path has no range estimate
    assert fix.bearing_deg is None


def test_projector_monocular_carries_distance_and_bearing():
    proj = RoomProjector.from_monocular(
        MonocularEstimator(640, 480), (0.0, 0.0, 90.0))
    t = FakeTrack(300.0, 100.0, 340.0, 400.0)
    fix = proj.locate(t)
    assert fix.method == "monocular"
    assert fix.distance_m is not None and fix.distance_m > 0
    assert fix.bearing_deg == pytest.approx(0.0, abs=1e-6)


def test_projector_needs_at_least_one_method():
    with pytest.raises(ValueError):
        RoomProjector()
