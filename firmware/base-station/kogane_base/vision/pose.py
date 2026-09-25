"""COCO-17 pose estimation and gesture reading, using ultralytics' own pose model.

Deliberately zero new dependencies: `yolov8n-pose.pt` comes from the same ultralytics
package that already does person detection (it auto-downloads on first use), so there is
no mediapipe/dlib build to fight with on Windows.

Layering:
  * `PoseEstimator` is the only part that touches ultralytics/torch. It returns plain
    numpy arrays.
  * everything else here is a pure function over a (17, 3) keypoint array, so the demo
    logic is unit-testable with no camera, no model and no GPU.

Image convention: +x right, +y DOWN. A raised hand therefore has a *smaller* y than the
shoulder, which is why the comparisons below look inverted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# COCO-17 keypoint order, exactly as ultralytics emits it.
COCO_KEYPOINTS: tuple[str, ...] = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)

NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_EAR, RIGHT_EAR = 3, 4
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16

# Pairs to draw a skeleton overlay.
SKELETON: tuple[tuple[int, int], ...] = (
    (LEFT_SHOULDER, RIGHT_SHOULDER), (LEFT_SHOULDER, LEFT_ELBOW), (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW), (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP), (RIGHT_SHOULDER, RIGHT_HIP), (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE), (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE), (RIGHT_KNEE, RIGHT_ANKLE),
    (NOSE, LEFT_SHOULDER), (NOSE, RIGHT_SHOULDER),
)

DEFAULT_MIN_CONF = 0.5


# --------------------------------------------------------------------------------------
# pure keypoint helpers
# --------------------------------------------------------------------------------------

def as_keypoints(arr) -> np.ndarray:
    """Coerce to a validated (17, 3) float array of (x_px, y_px, conf)."""
    a = np.asarray(arr, dtype=np.float64)
    if a.shape == (17, 2):                       # tolerate conf-less input
        a = np.hstack([a, np.ones((17, 1))])
    if a.shape != (17, 3):
        raise ValueError(f"expected COCO-17 keypoints of shape (17, 3), got {a.shape}")
    return a


def is_visible(kps: np.ndarray, idx: int, min_conf: float = DEFAULT_MIN_CONF) -> bool:
    """A keypoint counts as visible if its confidence clears the bar and it isn't (0,0)."""
    x, y, c = kps[idx]
    if c < min_conf:
        return False
    return not (x == 0.0 and y == 0.0)


def body_scale_px(kps: np.ndarray, min_conf: float = DEFAULT_MIN_CONF) -> float | None:
    """A scale reference in pixels so thresholds work at any distance.

    Prefers torso length (shoulder midpoint to hip midpoint), falls back to shoulder
    width (x2, roughly torso-comparable), then to head width. None if the person is too
    occluded to measure.
    """
    ls, rs = is_visible(kps, LEFT_SHOULDER, min_conf), is_visible(kps, RIGHT_SHOULDER, min_conf)
    lh, rh = is_visible(kps, LEFT_HIP, min_conf), is_visible(kps, RIGHT_HIP, min_conf)

    if (ls or rs) and (lh or rh):
        sh = _midpoint(kps, LEFT_SHOULDER, RIGHT_SHOULDER, min_conf)
        hp = _midpoint(kps, LEFT_HIP, RIGHT_HIP, min_conf)
        if sh is not None and hp is not None:
            torso = math.hypot(sh[0] - hp[0], sh[1] - hp[1])
            if torso > 1.0:
                return torso
    if ls and rs:
        width = abs(kps[LEFT_SHOULDER][0] - kps[RIGHT_SHOULDER][0])
        if width > 1.0:
            return width * 2.0
    if is_visible(kps, LEFT_EAR, min_conf) and is_visible(kps, RIGHT_EAR, min_conf):
        head = abs(kps[LEFT_EAR][0] - kps[RIGHT_EAR][0])
        if head > 1.0:
            return head * 6.0
    return None


def _midpoint(kps: np.ndarray, a: int, b: int,
              min_conf: float = DEFAULT_MIN_CONF) -> tuple[float, float] | None:
    """Midpoint of two keypoints, or whichever single one is visible."""
    va, vb = is_visible(kps, a, min_conf), is_visible(kps, b, min_conf)
    if va and vb:
        return (float(kps[a][0] + kps[b][0]) / 2.0, float(kps[a][1] + kps[b][1]) / 2.0)
    if va:
        return float(kps[a][0]), float(kps[a][1])
    if vb:
        return float(kps[b][0]), float(kps[b][1])
    return None


def is_arm_raised(kps: np.ndarray, side: str = "left",
                  min_conf: float = DEFAULT_MIN_CONF,
                  margin_frac: float = 0.15) -> bool:
    """True when that wrist is meaningfully above the same-side shoulder.

    `margin_frac` is a fraction of `body_scale_px`, so the test is distance-invariant:
    the wrist has to clear the shoulder by ~15% of a torso length by default, which
    rejects the noise you get from a hand resting near shoulder height.

    Pure function — no camera, no model. Unit-tested in tests/test_pose.py.
    """
    if side not in ("left", "right"):
        raise ValueError("side must be 'left' or 'right'")
    kps = as_keypoints(kps)
    wrist = LEFT_WRIST if side == "left" else RIGHT_WRIST
    shoulder = LEFT_SHOULDER if side == "left" else RIGHT_SHOULDER
    if not (is_visible(kps, wrist, min_conf) and is_visible(kps, shoulder, min_conf)):
        return False
    scale = body_scale_px(kps, min_conf)
    if scale is None:
        return False
    # y grows downward, so "above" means a smaller y
    return (kps[shoulder][1] - kps[wrist][1]) > margin_frac * scale


@dataclass
class GestureState:
    """What we can read off one person's pose this frame."""
    left_arm_raised: bool = False
    right_arm_raised: bool = False
    scale_px: float | None = None
    reason: str = ""

    @property
    def any_arm_raised(self) -> bool:
        return self.left_arm_raised or self.right_arm_raised

    @property
    def both_arms_raised(self) -> bool:
        return self.left_arm_raised and self.right_arm_raised

    @property
    def label(self) -> str:
        if self.both_arms_raised:
            return "BOTH ARMS UP"
        if self.left_arm_raised:
            return "LEFT ARM UP"
        if self.right_arm_raised:
            return "RIGHT ARM UP"
        return "-"


def classify_gesture(kps, min_conf: float = DEFAULT_MIN_CONF,
                     margin_frac: float = 0.15) -> GestureState:
    """Read gesture flags off a single person's COCO-17 keypoints. Pure function."""
    try:
        k = as_keypoints(kps)
    except ValueError as e:
        return GestureState(reason=f"bad keypoints: {e}")
    scale = body_scale_px(k, min_conf)
    if scale is None:
        return GestureState(reason="no body scale (torso/shoulders not visible)")
    return GestureState(
        left_arm_raised=is_arm_raised(k, "left", min_conf, margin_frac),
        right_arm_raised=is_arm_raised(k, "right", min_conf, margin_frac),
        scale_px=scale,
        reason="ok",
    )


@dataclass
class BeckonDetector:
    """Debounce a raised arm into a single 'come here' trigger.

    A hand that flickers above the shoulder for one frame is noise. Requiring
    `hold_frames` consecutive raised frames before firing, and `release_frames` lowered
    frames before re-arming, turns it into a usable command. Latching means `fire`
    returns True exactly once per gesture, not every frame the arm stays up.

    Pure state machine over booleans — testable with no camera.
    """
    hold_frames: int = 5
    release_frames: int = 3
    _up_run: int = field(default=0, repr=False)
    _down_run: int = field(default=0, repr=False)
    _latched: bool = field(default=False, repr=False)

    @property
    def armed(self) -> bool:
        """True while the gesture is being held and has already fired."""
        return self._latched

    def update(self, raised: bool) -> bool:
        """Feed one frame's raised/not-raised. Returns True on the firing frame only."""
        if raised:
            self._up_run += 1
            self._down_run = 0
            if not self._latched and self._up_run >= self.hold_frames:
                self._latched = True
                return True
            return False
        self._down_run += 1
        self._up_run = 0
        if self._latched and self._down_run >= self.release_frames:
            self._latched = False
        return False

    def reset(self) -> None:
        self._up_run = 0
        self._down_run = 0
        self._latched = False


def box_iou(a: tuple[float, float, float, float],
            b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two xyxy boxes. Pure function."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


@dataclass
class PersonPose:
    box: tuple[float, float, float, float]
    keypoints: np.ndarray            # (17, 3)
    conf: float


def match_pose_to_track(track, poses: list[PersonPose],
                        min_iou: float = 0.3) -> PersonPose | None:
    """Pick the pose whose box best overlaps a detector track. Pure function.

    The detector stays the single source of truth for track IDs; the pose model runs
    independently and we associate by geometry. Returns None if nothing overlaps enough,
    which is the right answer when the pose pass missed that person.
    """
    if not poses:
        return None
    tbox = (track.x1, track.y1, track.x2, track.y2)
    best, best_iou = None, 0.0
    for p in poses:
        i = box_iou(tbox, p.box)
        if i > best_iou:
            best, best_iou = p, i
    return best if best_iou >= min_iou else None


# --------------------------------------------------------------------------------------
# the only model-touching part
# --------------------------------------------------------------------------------------

class PoseEstimator:
    """yolov8n-pose wrapper returning COCO-17 keypoints per person.

    Optional and independently toggleable (CONFIG.pose_enabled) because it is a second
    full inference pass; on CPU that roughly halves the achievable frame rate.
    """

    def __init__(self, model_path: str = "yolov8n-pose.pt", device: str = "cpu",
                 conf: float = 0.35) -> None:
        from ultralytics import YOLO  # local import; only needed when CV is used

        self.model = YOLO(model_path)
        self.device = device
        self.conf = conf

    def estimate(self, image) -> list[PersonPose]:
        results = self.model.predict(
            image, conf=self.conf, device=self.device, verbose=False)
        out: list[PersonPose] = []
        if not results:
            return out
        r = results[0]
        kp = getattr(r, "keypoints", None)
        if kp is None or kp.data is None or r.boxes is None:
            return out
        data = kp.data.cpu().numpy()             # (N, 17, 3)
        boxes = r.boxes.xyxy.cpu().numpy()       # (N, 4)
        confs = r.boxes.conf.cpu().numpy()       # (N,)
        for i in range(min(len(data), len(boxes))):
            x1, y1, x2, y2 = (float(v) for v in boxes[i])
            out.append(PersonPose((x1, y1, x2, y2),
                                  np.asarray(data[i], dtype=np.float64),
                                  float(confs[i])))
        return out


def draw_pose(cv2, img, kps: np.ndarray, min_conf: float = DEFAULT_MIN_CONF,
              color: tuple[int, int, int] = (0, 255, 255)) -> None:
    """Overlay a skeleton. `cv2` is passed in so this module never imports it eagerly."""
    k = as_keypoints(kps)
    for a, b in SKELETON:
        if is_visible(k, a, min_conf) and is_visible(k, b, min_conf):
            cv2.line(img, (int(k[a][0]), int(k[a][1])), (int(k[b][0]), int(k[b][1])),
                     color, 2)
    for i in range(17):
        if is_visible(k, i, min_conf):
            cv2.circle(img, (int(k[i][0]), int(k[i][1])), 3, color, -1)
