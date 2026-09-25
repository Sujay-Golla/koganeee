"""Gesture logic over synthetic COCO-17 keypoints. No camera, no model, no torch.

Remember the image convention: +y points DOWN, so a raised wrist has a SMALLER y than
the shoulder it belongs to.
"""
from __future__ import annotations

import numpy as np
import pytest

from kogane_base.vision.pose import (BeckonDetector, LEFT_ELBOW, LEFT_HIP, LEFT_SHOULDER,
                                     LEFT_WRIST, NOSE, RIGHT_ELBOW, RIGHT_HIP,
                                     RIGHT_SHOULDER, RIGHT_WRIST, as_keypoints,
                                     body_scale_px, box_iou, classify_gesture,
                                     is_arm_raised, is_visible, match_pose_to_track,
                                     PersonPose)


def standing_person(scale: float = 1.0, cx: float = 320.0, cy: float = 240.0,
                    conf: float = 0.9) -> np.ndarray:
    """A neutral standing pose: arms down, torso 100*scale px tall.

    Coordinates are laid out from the shoulder line so the tests can reason in torso
    fractions rather than raw pixels.
    """
    s = scale
    sh_y = cy - 50 * s
    hip_y = cy + 50 * s          # torso = 100*s px
    k = np.zeros((17, 3), dtype=np.float64)

    def put(i, x, y, c=conf):
        k[i] = (x, y, c)

    put(NOSE, cx, sh_y - 30 * s)
    put(1, cx - 8 * s, sh_y - 34 * s)      # left_eye
    put(2, cx + 8 * s, sh_y - 34 * s)      # right_eye
    put(3, cx - 14 * s, sh_y - 30 * s)     # left_ear
    put(4, cx + 14 * s, sh_y - 30 * s)     # right_ear
    put(LEFT_SHOULDER, cx - 25 * s, sh_y)
    put(RIGHT_SHOULDER, cx + 25 * s, sh_y)
    put(LEFT_ELBOW, cx - 30 * s, sh_y + 35 * s)
    put(RIGHT_ELBOW, cx + 30 * s, sh_y + 35 * s)
    put(LEFT_WRIST, cx - 32 * s, sh_y + 70 * s)     # hanging down
    put(RIGHT_WRIST, cx + 32 * s, sh_y + 70 * s)
    put(LEFT_HIP, cx - 18 * s, hip_y)
    put(RIGHT_HIP, cx + 18 * s, hip_y)
    put(13, cx - 18 * s, hip_y + 50 * s)   # knees
    put(14, cx + 18 * s, hip_y + 50 * s)
    put(15, cx - 18 * s, hip_y + 100 * s)  # ankles
    put(16, cx + 18 * s, hip_y + 100 * s)
    return k


def raise_arm(k: np.ndarray, side: str, above_px: float) -> np.ndarray:
    """Move one wrist `above_px` pixels above that shoulder."""
    k = k.copy()
    w = LEFT_WRIST if side == "left" else RIGHT_WRIST
    sh = LEFT_SHOULDER if side == "left" else RIGHT_SHOULDER
    k[w] = (k[sh][0], k[sh][1] - above_px, k[w][2])
    return k


# ---- input coercion ----

def test_as_keypoints_accepts_17x3():
    k = standing_person()
    assert as_keypoints(k).shape == (17, 3)


def test_as_keypoints_fills_conf_for_17x2():
    out = as_keypoints(np.zeros((17, 2)))
    assert out.shape == (17, 3)
    assert np.all(out[:, 2] == 1.0)


def test_as_keypoints_rejects_wrong_shape():
    with pytest.raises(ValueError, match="COCO-17"):
        as_keypoints(np.zeros((12, 3)))


def test_zero_point_is_not_visible_even_at_high_conf():
    k = standing_person()
    k[LEFT_WRIST] = (0.0, 0.0, 0.99)
    assert not is_visible(k, LEFT_WRIST)


def test_low_conf_point_is_not_visible():
    k = standing_person()
    k[LEFT_WRIST] = (100.0, 100.0, 0.1)
    assert not is_visible(k, LEFT_WRIST)


# ---- scale ----

def test_body_scale_is_torso_length():
    k = standing_person(scale=1.0)
    assert body_scale_px(k) == pytest.approx(100.0, abs=1.0)
    k2 = standing_person(scale=2.0)
    assert body_scale_px(k2) == pytest.approx(200.0, abs=1.0)


def test_body_scale_falls_back_to_shoulders_when_hips_hidden():
    k = standing_person()
    k[LEFT_HIP][2] = 0.0
    k[RIGHT_HIP][2] = 0.0
    assert body_scale_px(k) == pytest.approx(100.0, abs=1.0)   # 50 px shoulders * 2


def test_body_scale_none_when_torso_unmeasurable():
    k = standing_person()
    for i in (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP, 3, 4):
        k[i][2] = 0.0
    assert body_scale_px(k) is None


# ---- the raised-arm predicate ----

def test_neutral_pose_has_no_arm_raised():
    k = standing_person()
    assert not is_arm_raised(k, "left")
    assert not is_arm_raised(k, "right")


def test_clearly_raised_left_arm_detected():
    k = raise_arm(standing_person(), "left", above_px=40.0)   # 40% of torso
    assert is_arm_raised(k, "left")
    assert not is_arm_raised(k, "right")


def test_clearly_raised_right_arm_detected():
    k = raise_arm(standing_person(), "right", above_px=40.0)
    assert is_arm_raised(k, "right")
    assert not is_arm_raised(k, "left")


def test_hand_just_barely_above_shoulder_is_rejected_as_noise():
    """5 px above a 100 px torso is 5%, under the 15% margin."""
    k = raise_arm(standing_person(), "left", above_px=5.0)
    assert not is_arm_raised(k, "left")


def test_margin_is_scale_invariant():
    """The same gesture at half size and double size must classify identically."""
    for scale in (0.5, 1.0, 3.0):
        torso = 100.0 * scale
        up = raise_arm(standing_person(scale=scale), "left", above_px=0.40 * torso)
        barely = raise_arm(standing_person(scale=scale), "left", above_px=0.05 * torso)
        assert is_arm_raised(up, "left"), scale
        assert not is_arm_raised(barely, "left"), scale


def test_raised_arm_false_when_wrist_not_visible():
    k = raise_arm(standing_person(), "left", above_px=40.0)
    k[LEFT_WRIST][2] = 0.0
    assert not is_arm_raised(k, "left")


def test_raised_arm_false_when_no_scale_available():
    k = raise_arm(standing_person(), "left", above_px=40.0)
    for i in (RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP, 3, 4):
        k[i][2] = 0.0
    # left shoulder alone gives no torso and no shoulder width -> undecidable
    assert not is_arm_raised(k, "left")


def test_bad_side_rejected():
    with pytest.raises(ValueError):
        is_arm_raised(standing_person(), "up")


# ---- classify_gesture ----

def test_classify_neutral():
    g = classify_gesture(standing_person())
    assert not g.any_arm_raised
    assert not g.both_arms_raised
    assert g.label == "-"
    assert g.reason == "ok"
    assert g.scale_px == pytest.approx(100.0, abs=1.0)


def test_classify_single_arm_labels():
    left = classify_gesture(raise_arm(standing_person(), "left", 40.0))
    assert left.any_arm_raised and not left.both_arms_raised
    assert left.label == "LEFT ARM UP"

    right = classify_gesture(raise_arm(standing_person(), "right", 40.0))
    assert right.label == "RIGHT ARM UP"


def test_classify_both_arms():
    k = raise_arm(raise_arm(standing_person(), "left", 40.0), "right", 40.0)
    g = classify_gesture(k)
    assert g.both_arms_raised
    assert g.any_arm_raised
    assert g.label == "BOTH ARMS UP"


def test_classify_degrades_on_unusable_input():
    g = classify_gesture(np.zeros((17, 3)))
    assert not g.any_arm_raised
    assert "no body scale" in g.reason


def test_classify_reports_bad_shape_instead_of_raising():
    g = classify_gesture(np.zeros((5, 3)))
    assert not g.any_arm_raised
    assert "bad keypoints" in g.reason


# ---- BeckonDetector state machine ----

def test_beckon_needs_sustained_hold_before_firing():
    b = BeckonDetector(hold_frames=5, release_frames=3)
    fires = [b.update(True) for _ in range(4)]
    assert fires == [False, False, False, False]
    assert b.update(True) is True          # 5th consecutive frame fires
    assert b.armed


def test_beckon_fires_exactly_once_per_gesture():
    b = BeckonDetector(hold_frames=3, release_frames=2)
    fired = [b.update(True) for _ in range(12)]
    assert fired.count(True) == 1
    assert fired.index(True) == 2


def test_beckon_flicker_never_fires():
    b = BeckonDetector(hold_frames=5, release_frames=3)
    for _ in range(30):
        assert b.update(True) is False
        assert b.update(False) is False
    assert not b.armed


def test_beckon_rearms_after_release_then_fires_again():
    b = BeckonDetector(hold_frames=3, release_frames=2)
    assert [b.update(True) for _ in range(3)][-1] is True
    b.update(False)
    assert b.armed            # one lowered frame is not enough to release
    b.update(False)
    assert not b.armed        # released after 2
    assert [b.update(True) for _ in range(3)][-1] is True


def test_beckon_partial_release_does_not_rearm():
    b = BeckonDetector(hold_frames=2, release_frames=4)
    b.update(True)
    assert b.update(True) is True
    for _ in range(3):
        b.update(False)
    assert b.armed
    # coming back up while still latched must not fire again
    assert b.update(True) is False


def test_beckon_reset_clears_state():
    b = BeckonDetector(hold_frames=2)
    b.update(True)
    b.update(True)
    assert b.armed
    b.reset()
    assert not b.armed
    assert b.update(True) is False       # run counter restarted


# ---- box IoU and pose/track association ----

def test_iou_identical_boxes_is_one():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)


def test_iou_disjoint_boxes_is_zero():
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_iou_touching_edges_is_zero():
    assert box_iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0


def test_iou_half_overlap():
    # 10x10 and 10x10 sharing a 5x10 strip: inter 50, union 150
    assert box_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)


def test_iou_degenerate_box_is_zero():
    assert box_iou((0, 0, 0, 0), (0, 0, 10, 10)) == 0.0


class FakeTrack:
    def __init__(self, x1, y1, x2, y2, track_id=1):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.track_id = track_id


def test_match_pose_picks_best_overlap():
    t = FakeTrack(100, 100, 200, 400)
    close = PersonPose((105, 102, 198, 396), standing_person(), 0.9)
    far = PersonPose((400, 100, 500, 400), standing_person(), 0.9)
    assert match_pose_to_track(t, [far, close]) is close


def test_match_pose_returns_none_below_min_iou():
    t = FakeTrack(100, 100, 200, 400)
    barely = PersonPose((195, 395, 300, 500), standing_person(), 0.9)
    assert match_pose_to_track(t, [barely], min_iou=0.3) is None


def test_match_pose_returns_none_with_no_poses():
    assert match_pose_to_track(FakeTrack(0, 0, 10, 10), []) is None
