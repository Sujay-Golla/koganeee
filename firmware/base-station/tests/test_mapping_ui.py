"""Keep the readable dashboard honest when measurements are stale or unavailable."""
import numpy as np

from kogane_base.tools.mapping_demo import TargetState
from kogane_base.tools.mapping_multi import CameraView
from kogane_base.tools.mapping_ui import presentation, radar_message, render
from kogane_base.vision.sources import Frame


def scene():
    target = TargetState()
    target.observe(2.5, 2.4, 7, 10)
    views = [CameraView(i, (x, 0, 0)) for i, x in ((2, 2.3), (1, 2.7))]
    for view in views:
        view.status = "LIVE"
        view.frame = Frame(np.zeros((480, 640, 3), np.uint8), 1, 10)
    state = dict(target=target, valid=True, depth_m=2.4, status="STEREO VALID",
                 room_aligned=False, calibration_warning=True, support_fraction=.4,
                 skew_ms=12, elapsed_s=18)
    return views, state


def test_old_or_rejected_depth_cannot_appear_as_current_distance():
    views, stereo = scene()
    live = presentation(stereo, views, 10.1, (5, 4))
    assert live["depth"] == 2.4 and live["lateral"] == "Near centre"
    stale = presentation(stereo, views, 11, (5, 4))
    assert not stale["live"] and stale["depth"] is None and stale["forward"] == "—"
    stereo["valid"] = False
    assert presentation(stereo, views, 10.1, (5, 4))["depth"] is None
    stereo.update(valid=True, depth_m=float("nan"))
    assert not presentation(stereo, views, 10.1, (5, 4))["live"]


def test_radar_silence_is_not_presented_as_a_fresh_empty_room():
    assert radar_message("LIVE / 0 TARGETS", [])[0] == "0 detections"
    assert radar_message("STALE", [])[0] == "Paused"
    assert radar_message("ERROR / CHECK PORT", [])[0] == "Check connection"


def test_dashboard_handles_lost_targets_and_diagnostics_without_valid_numbers():
    views, stereo = scene()
    stereo.update(valid=False, status="WAITING FOR RELIABLE STEREO MATCH", show_details=True)
    overlay = render(views, now=11, room=(5, 4), stereo=stereo,
                     radar_points=[(2.5, 2.4)], radar_status="STALE", recording=True)
    assert overlay.shape == (720, 1280, 3) and overlay.dtype == np.uint8
