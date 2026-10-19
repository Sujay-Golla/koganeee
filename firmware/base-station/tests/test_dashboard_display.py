"""Native-density drawing, window sizing and fixed recording dimensions."""
import cv2
import numpy as np
import pytest

from kogane_base.tools.dashboard_display import render_size, recording_frame, size_from_width
from kogane_base.tools.mapping_demo import TargetState
from kogane_base.tools.mapping_multi import CameraView
from kogane_base.tools.mapping_ui import render
from kogane_base.vision.sources import Frame


@pytest.mark.parametrize("size", [(1920, 1080), (2560, 1440), (3840, 2160)])
def test_dashboard_rasterizes_text_at_requested_resolution(size):
    target = TargetState()
    target.observe(2.5, 2.4, 7, 10)
    view = CameraView(2, (2.3, 0, 0), status="LIVE")
    view.frame = Frame(np.full((480, 640, 3), 90, np.uint8), 1, 10)
    state = dict(target=target, valid=True, depth_m=2.4, position_source="radar",
                 status="RADAR POSITION VALID", map_objects=True,
                 objects=[dict(identity=1, label="Chair", xy=(1, 3), age_s=0, visible=True)])
    image = render([view], now=10.1, room=(5, 4), stereo=state, size=size, preview=True)
    assert image.shape == (size[1], size[0], 3) and image.dtype == np.uint8
    low = render([view], now=10.1, room=(5, 4), stereo=state, preview=True)
    enlarged = cv2.resize(low, size, interpolation=cv2.INTER_LINEAR)
    # The heading is freshly rasterized; it is not a stretched 720p bitmap.
    s = size[0]/1280
    region = (slice(round(77*s), round(121*s)), slice(round(32*s), round(350*s)))
    assert np.mean(np.abs(image[region].astype(float)-enlarged[region])) > .5


def test_window_pixels_follow_fullscreen_and_fixed_recording_size(monkeypatch):
    monkeypatch.setattr(cv2, "getWindowImageRect", lambda name: (0, 0, 3840, 2160))
    assert render_size("dashboard") == (3840, 2160)
    monkeypatch.setattr(cv2, "getWindowImageRect", lambda name: (0, 0, 2560, 1600))
    assert render_size("dashboard") == (2560, 1440)
    monkeypatch.setattr(cv2, "getWindowImageRect", lambda name: (0, 0, 960, 540))
    assert render_size("dashboard", record_size=(1920, 1080)) == (1920, 1080)
    assert render_size("dashboard", forced_width=2560) == (2560, 1440)


def test_recording_resizes_only_the_finished_native_frame():
    image = np.full((1440, 2560, 3), 120, np.uint8)
    encoded = recording_frame(image, (1920, 1080))
    assert encoded.shape == (1080, 1920, 3) and np.all(encoded == 120)
    assert recording_frame(encoded, (1920, 1080)) is encoded
    with pytest.raises(ValueError):
        size_from_width(1234)


def test_missing_window_rectangle_falls_back_to_standard_size(monkeypatch):
    def unavailable(name):
        raise cv2.error("unsupported backend")
    monkeypatch.setattr(cv2, "getWindowImageRect", unavailable)
    assert render_size("dashboard") == (1280, 720)
