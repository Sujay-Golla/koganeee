"""Tests for the mmWave simulator and the room-frame round trip it depends on.

The last test is the end-to-end one: the exact datagram bytes `kogane-mmwave-sim` sends go
through `unpack` -> `BaseStation._on_frame` -> Kalman -> staleness -> the real control loop,
and VELOCITY setpoints come out. No socket is bound; the live socket run is a manual step
documented in the README.
"""
from __future__ import annotations

import asyncio
import math

import pytest

from kogane_base.config import CONFIG
from kogane_base.link.failsafe import Freshness
from kogane_base.main import BaseStation
from kogane_base.protocol import CtrlMode, MsgType, unpack, unpack_setpoint
from kogane_base.tools.mmwave_sim import _make_path, build_datagram, build_parser
from kogane_base.tracking.mmwave import (detections_from_payload, node_frame_to_room,
                                         room_to_node_frame)


# ---- the room-frame inverse the simulator relies on -----------------------
@pytest.mark.parametrize("node_id", [0, 1, 99])   # 99 is deliberately unmapped
@pytest.mark.parametrize("x_m,y_m", [(0.0, 0.0), (1.0, 2.0), (-1.5, 3.25), (4.0, 5.0)])
def test_room_to_node_frame_is_the_inverse_of_node_frame_to_room(node_id, x_m, y_m):
    x_mm, y_mm = room_to_node_frame(node_id, x_m, y_m)
    back = node_frame_to_room(node_id, x_mm, y_mm)
    assert back == pytest.approx((x_m, y_m), abs=1e-3)   # 1 mm rounding


def test_room_to_node_frame_returns_whole_millimetres():
    x_mm, y_mm = room_to_node_frame(0, 1.23456, 2.34567)
    assert isinstance(x_mm, int) and isinstance(y_mm, int)


def test_unmapped_node_passes_coordinates_straight_through():
    assert room_to_node_frame(12345, 1.5, -2.5) == (1500, -2500)


# ---- paths ---------------------------------------------------------------
def test_static_path_does_not_move():
    path = _make_path("static", 2.0, 2.5, 1.0, 1.0, 2.0)
    assert path(0.0) == path(7.5) == (2.0, 2.5)


def test_circle_path_keeps_its_radius():
    path = _make_path("circle", 2.0, 2.5, 1.0, 1.25, 2.0)
    for t in [0.0, 0.7, 3.3, 11.9]:
        x, y = path(t)
        assert math.hypot(x - 2.0, y - 2.5) == pytest.approx(1.25)


def test_circle_path_walks_at_the_requested_speed():
    speed, radius = 1.4, 1.1
    path = _make_path("circle", 0.0, 0.0, speed, radius, 2.0)
    dt = 1e-3
    a, b = path(2.0), path(2.0 + dt)
    assert math.hypot(b[0] - a[0], b[1] - a[1]) / dt == pytest.approx(speed, rel=1e-3)


def test_line_path_stays_inside_its_length_and_reverses():
    length, speed = 2.0, 1.0
    path = _make_path("line", 2.0, 2.5, speed, 1.0, length)
    xs = [path(t)[0] for t in [i * 0.05 for i in range(200)]]
    assert min(xs) == pytest.approx(2.0 - length / 2, abs=0.05)
    assert max(xs) == pytest.approx(2.0 + length / 2, abs=0.05)
    assert all(y == 2.5 for _x, y in (path(t) for t in [0.0, 1.0, 2.0]))
    # it must turn around, not run off
    assert any(b < a for a, b in zip(xs, xs[1:]))
    assert any(b > a for a, b in zip(xs, xs[1:]))


def test_square_path_stays_on_its_perimeter():
    side = 2.0
    path = _make_path("square", 2.0, 2.5, 1.0, 1.0, side)
    h = side / 2
    for t in [i * 0.13 for i in range(100)]:
        x, y = path(t)
        on_edge = (math.isclose(abs(x - 2.0), h, abs_tol=1e-6)
                   or math.isclose(abs(y - 2.5), h, abs_tol=1e-6))
        assert on_edge, f"({x}, {y}) is not on the square at t={t}"


def test_figure8_returns_to_the_centre_twice_per_lap():
    path = _make_path("figure8", 0.0, 0.0, 1.0, 1.0, 2.0)
    assert path(0.0) == pytest.approx((0.0, 0.0))
    assert path(math.pi) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_unknown_path_is_rejected():
    with pytest.raises(ValueError):
        _make_path("spiral", 0, 0, 1, 1, 1)


# ---- datagram construction ----------------------------------------------
def test_datagram_places_the_target_back_on_the_intended_room_point():
    data = build_datagram(node_id=0, x_m=1.75, y_m=3.25, speed_cms=42, seq=5)
    frame = unpack(data)
    assert frame is not None
    assert frame.msg_type == MsgType.MMWAVE_TARGETS
    assert frame.src_id == 0
    assert frame.seq == 5
    dets = detections_from_payload(frame.src_id, frame.payload)
    assert len(dets) == 1
    assert (dets[0].x_m, dets[0].y_m) == pytest.approx((1.75, 3.25), abs=1e-3)
    assert dets[0].speed_ms == pytest.approx(0.42)


def test_datagram_survives_a_node_pose_change():
    """The simulator must follow CONFIG.node_poses, not hardcode a transform."""
    for node_id in (0, 1):
        data = build_datagram(node_id, 2.0, 2.0)
        frame = unpack(data)
        dets = detections_from_payload(frame.src_id, frame.payload)
        assert (dets[0].x_m, dets[0].y_m) == pytest.approx((2.0, 2.0), abs=1e-3)


def test_cli_defaults_are_sane():
    args = build_parser().parse_args([])
    assert args.port == CONFIG.udp_port
    assert args.rate == 10.0                # the LD2450's own report rate
    assert args.path == "circle"
    assert not args.fake_drone


def test_cli_accepts_the_documented_flags():
    args = build_parser().parse_args(
        ["--path", "line", "--rate", "25", "--speed", "0.8", "--node-id", "1",
         "--center", "1.0,2.0", "--duration", "3", "--fake-drone"])
    assert (args.path, args.rate, args.speed, args.node_id) == ("line", 25.0, 0.8, 1)
    assert args.center == "1.0,2.0"
    assert args.fake_drone


# ---- end to end: simulator bytes -> setpoints ----------------------------
def test_simulated_walk_drives_the_control_loop_to_velocity_setpoints(monkeypatch):
    """The full chain, minus the socket: datagram -> fusion -> freshness -> setpoint."""
    monkeypatch.setattr(CONFIG, "loop_hz", 200.0)     # keep the test short
    monkeypatch.setattr(CONFIG, "vision_enabled", False)

    bs = BaseStation()
    bs.drone_xy = (0.5, 0.5)
    sent: list[tuple[int, bytes]] = []
    monkeypatch.setattr(bs.udp, "send",
                        lambda mt, payload, addr, src_id=0: sent.append((mt, payload)))

    path = _make_path("circle", CONFIG.room_w_m / 2, CONFIG.room_l_m / 2, 1.0, 1.0, 2.0)
    transitions: list[Freshness] = []
    real_poll = bs.freshness.poll

    def spy_poll(now):
        t = real_poll(now)
        if t is not None:
            transitions.append(t)
        return t

    monkeypatch.setattr(bs.freshness, "poll", spy_poll)

    async def feed():
        """Stand in for the simulator process: same bytes, straight into the UDP handler."""
        for i in range(20):
            x_m, y_m = path(i * 0.1)
            frame = unpack(build_datagram(0, x_m, y_m, speed_cms=100, seq=i))
            assert frame is not None, "the simulator must emit a valid KGN datagram"
            bs._on_frame(frame, ("127.0.0.1", 40000))
            await asyncio.sleep(0.01)

    async def go():
        loop_task = asyncio.create_task(bs._control_loop())
        await feed()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())

    assert bs.filter.initialised, "mmWave datagrams must seed the Kalman filter"
    assert Freshness.ACQUIRED in transitions, "the staleness monitor must report ACQUIRED"
    assert sent, "the control loop must emit setpoints once a target is being tracked"
    modes = {CtrlMode(unpack_setpoint(payload).ctrl_mode) for _mt, payload in sent}
    assert all(mt == MsgType.SETPOINT for mt, _p in sent)
    assert CtrlMode.VELOCITY in modes, f"expected following, saw {modes}"
    # the fused estimate should be somewhere on the walked circle, not at the origin
    px, py = bs.filter.position
    assert math.hypot(px - CONFIG.room_w_m / 2, py - CONFIG.room_l_m / 2) < 1.6
