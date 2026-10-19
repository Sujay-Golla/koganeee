import math

import numpy as np
import pytest

from kogane_base.net.sink import ListSink
from kogane_base.protocol import MsgType
from kogane_base.tools.demo_assistant import DisplayOnlySink, card, command_intent
from kogane_base.tools.mapping_demo import TargetState, plot_point, render_overlay


@pytest.mark.parametrize("text,intent", [
    ("Show me the weather today!", "weather"),
    ("Kogane show me my tasks for today", "tasks"),
    ("show me the picture", None),
    ("new task buy groceries", "tasks"),
    ("arm", None), ("follow me", None), ("land", None),
    ("this unrelated conversation mentions weather", None),
])
def test_only_demo_intents(text, intent):
    assert command_intent(text) == intent


def test_display_transport_cannot_emit_control():
    raw = ListSink()
    sink = DisplayOnlySink(raw)
    sink.send(MsgType.SCREEN_FRAME, b"image")
    for msg in MsgType:
        if msg != MsgType.SCREEN_FRAME:
            with pytest.raises(ValueError):
                sink.send(msg, b"blocked")
    assert raw.frames == [(int(MsgType.SCREEN_FRAME), b"image")]


def test_stale_person_and_identity_change_do_not_leave_live_ghosts():
    target = TargetState()
    target.observe(1, 2, 3, 10)
    assert target.fresh(10.1)
    assert not target.fresh(11)
    assert not target.fresh(9)
    target.observe(3, 4, 5, 11)
    assert target.xy == (3, 4)
    assert list(target.trail) == [(3, 4)]
    assert not target.observe(math.nan, 2, 5, 12)
    assert not target.observe(0, 0, 5, 9)
    assert target.xy == (3, 4)


def test_outside_map_values_are_not_clamped_into_plausible_locations():
    room, bounds = (4, 5), (10, 20, 410, 520)
    assert plot_point((0, 0), room, bounds) == (10, 520)
    assert plot_point((4, 5), room, bounds) == (410, 20)
    assert plot_point((-0.1, 2), room, bounds) is None
    assert plot_point((2, 5.1), room, bounds) is None


def test_demo_artifact_sizes_and_overlay_with_no_target():
    for kind in ("ready", "weather", "tasks"):
        image = card(kind)
        assert image.mode == "RGB" and image.size == (320, 240)
    image = np.zeros((480, 640, 3), np.uint8)
    overlay = render_overlay(image, [], TargetState(), now=1)
    assert overlay.shape == (720, 1280, 3)
