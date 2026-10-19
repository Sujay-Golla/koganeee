"""End-to-end check that `BaseStation._control_loop` really holds when tracking dies.

No sockets are opened: `UdpEndpoint.send` is a no-op until `start()` binds a transport,
so we just record what the loop tried to send.

Both time and `asyncio.sleep` are faked inside `kogane_base.main`, so the loop runs a
precise number of cycles with a precise amount of simulated time per cycle. Relying on
real sleeps here would be flaky: Windows' default timer granularity is ~15 ms, so a
nominal 0.5 ms period actually yields ~60 cycles/second rather than 2000.
"""
from __future__ import annotations

import asyncio

import pytest

from kogane_base.config import CONFIG
from kogane_base.main import BaseStation
from kogane_base.protocol import CtrlMode, DS_F_POS_VALID, MsgType, unpack_setpoint
from kogane_base.vision.runner import VisionObservation

LOOP_HZ = 30.0
PERIOD = 1.0 / LOOP_HZ
STALE_S = 1.0
CYCLES_TO_STALE = int(STALE_S / PERIOD)      # 30 cycles of silence


class _StopLoop(Exception):
    """Breaks out of the otherwise-infinite control loop after a set number of cycles."""


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def monotonic(self) -> float:
        return self.t

    def advance(self, d: float) -> None:
        self.t += d


class FakeTime:
    """Stands in for the `time` module inside kogane_base.main."""

    def __init__(self, clock: FakeClock) -> None:
        self.monotonic = clock.monotonic


class FakeAsyncio:
    """Stands in for the `asyncio` module inside kogane_base.main.

    `sleep` advances simulated time by exactly the requested amount and yields to the
    event loop, then stops the loop once `max_cycles` is reached.
    """

    def __init__(self, clock: FakeClock, max_cycles: int, on_cycle=None) -> None:
        self._clock = clock
        self._max = max_cycles
        self._on_cycle = on_cycle
        self.cycles = 0

    async def sleep(self, delay: float) -> None:
        self.cycles += 1
        if self.cycles > self._max:
            raise _StopLoop
        self._clock.advance(delay)
        if self._on_cycle is not None:
            self._on_cycle(self.cycles, self._clock)
        await asyncio.sleep(0)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(CONFIG, "target_stale_s", STALE_S)
    monkeypatch.setattr(CONFIG, "loop_hz", LOOP_HZ)
    monkeypatch.setattr(CONFIG, "vision_enabled", False)
    return monkeypatch


def build(monkeypatch, clock: FakeClock):
    """A BaseStation with faked time and a send recorder."""
    from kogane_base import main as main_mod

    monkeypatch.setattr(main_mod, "time", FakeTime(clock))
    bs = BaseStation()
    sent: list[tuple[int, bytes]] = []
    monkeypatch.setattr(bs.udp, "send",
                        lambda mt, payload, addr, src_id=0: sent.append((mt, payload)))
    return bs, sent


def run_loop(monkeypatch, bs, clock: FakeClock, cycles: int, on_cycle=None) -> FakeAsyncio:
    from kogane_base import main as main_mod

    fake = FakeAsyncio(clock, cycles, on_cycle)
    monkeypatch.setattr(main_mod, "asyncio", fake)

    async def go():
        try:
            await bs._control_loop()
        except _StopLoop:
            pass

    asyncio.run(go())
    return fake


def modes(sent):
    out = []
    for msg_type, payload in sent:
        assert msg_type == MsgType.SETPOINT
        sp = unpack_setpoint(payload)
        assert sp is not None, "control loop emitted an unparseable setpoint"
        out.append(CtrlMode(sp.ctrl_mode))
    return out


def test_nothing_is_sent_before_the_filter_is_initialised(env):
    clock = FakeClock()
    bs, sent = build(env, clock)
    run_loop(env, bs, clock, cycles=60)
    assert sent == [], "must not command the drone before any target has been seen"


def test_velocity_then_hold_when_measurements_stop(env):
    """The core failsafe: fresh -> VELOCITY, stale -> HOLD, and it never reverts."""
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.drone_xy = (0.0, 0.0)
    bs.filter.update(3.0, 0.0)
    bs.freshness.mark(clock.t)          # one real measurement, then silence

    run_loop(env, bs, clock, cycles=CYCLES_TO_STALE * 3)

    seq = modes(sent)
    assert len(seq) > CYCLES_TO_STALE
    assert seq[0] is CtrlMode.VELOCITY, "should follow while the target is fresh"
    assert seq[-1] is CtrlMode.HOLD, "should hold once measurements go stale"
    first_hold = seq.index(CtrlMode.HOLD)
    assert CtrlMode.VELOCITY not in seq[first_hold:], \
        "must not resume velocity commands without a new measurement"
    # the switch must happen right at the timeout, not early and not late
    assert first_hold == pytest.approx(CYCLES_TO_STALE, abs=2)


def test_hold_is_entered_exactly_once_so_it_logs_once(env):
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.filter.update(1.0, 1.0)
    bs.freshness.mark(clock.t)
    run_loop(env, bs, clock, cycles=CYCLES_TO_STALE * 4)

    seq = modes(sent)
    flips = sum(1 for a, b in zip(seq, seq[1:]) if a is not b)
    assert flips == 1, f"expected a single VELOCITY->HOLD transition, saw {flips} flips"


def test_hold_setpoint_is_all_zero_velocity(env):
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.filter.update(2.0, 2.0)
    bs.freshness.mark(clock.t - 60.0)      # already ancient
    run_loop(env, bs, clock, cycles=20)

    assert sent, "a stale target should still keep the link alive with HOLD"
    for _msg_type, payload in sent:
        sp = unpack_setpoint(payload)
        assert CtrlMode(sp.ctrl_mode) is CtrlMode.HOLD
        assert (sp.vx_cms, sp.vy_cms, sp.vz_cms, sp.yaw_rate_cds) == (0, 0, 0, 0)


def test_continuous_measurements_keep_it_in_velocity(env):
    """While observations keep arriving the loop must never drop into HOLD."""
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.drone_xy = (0.0, 0.0)
    bs.filter.update(3.0, 0.0)
    bs.freshness.mark(clock.t)

    def keep_fresh(_cycle, ck):
        bs.freshness.mark(ck.t)
        bs.filter.update(3.0, 0.0)

    run_loop(env, bs, clock, cycles=CYCLES_TO_STALE * 5, on_cycle=keep_fresh)

    seq = modes(sent)
    assert len(seq) > CYCLES_TO_STALE * 2
    assert all(m is CtrlMode.VELOCITY for m in seq), \
        "a continuously tracked target should never trigger the failsafe"


def test_intermittent_measurements_inside_the_window_never_hold(env):
    """A 0.5 s gap with a 1.0 s timeout is a dropout, not a loss."""
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.filter.update(3.0, 0.0)
    bs.freshness.mark(clock.t)

    def occasionally(cycle, ck):
        if cycle % 15 == 0:               # every 0.5 s of simulated time
            bs.freshness.mark(ck.t)

    run_loop(env, bs, clock, cycles=CYCLES_TO_STALE * 4, on_cycle=occasionally)
    assert all(m is CtrlMode.VELOCITY for m in modes(sent))


def test_reacquisition_resumes_velocity(env):
    """After a loss, a fresh measurement must bring following back."""
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.filter.update(3.0, 0.0)
    bs.freshness.mark(clock.t)

    def late_reacquire(cycle, ck):
        if cycle == CYCLES_TO_STALE * 2:
            bs.freshness.mark(ck.t)

    run_loop(env, bs, clock, cycles=CYCLES_TO_STALE * 3, on_cycle=late_reacquire)

    seq = modes(sent)
    assert CtrlMode.HOLD in seq
    assert seq[-1] is CtrlMode.VELOCITY
    # VELOCITY -> HOLD -> VELOCITY
    flips = [b for a, b in zip(seq, seq[1:]) if a is not b]
    assert flips == [CtrlMode.HOLD, CtrlMode.VELOCITY]


def test_measured_dt_is_used_not_the_nominal_period(env):
    """Task 3: dt comes from the clock, so a stalled host does not corrupt the filter."""
    clock = FakeClock()
    bs, sent = build(env, clock)
    bs.filter.update(1.0, 1.0)
    bs.freshness.mark(clock.t)

    seen_dt: list[float] = []
    real_predict = bs.filter.predict
    bs.filter.predict = lambda dt: (seen_dt.append(dt), real_predict(dt))[1]

    def stall(cycle, ck):
        if cycle == 5:
            ck.advance(10.0)          # host suspended for 10 s

    run_loop(env, bs, clock, cycles=12, on_cycle=stall)

    assert seen_dt, "predict should have been called"
    assert max(seen_dt) <= 0.5 + 1e-9, "dt must be clamped against a pathological stall"
    assert max(seen_dt) > PERIOD, "the stall should have produced a dt above the nominal"
    normal = [d for d in seen_dt if d < 0.5]
    assert all(d == pytest.approx(PERIOD, abs=1e-6) for d in normal)


# ---- input plumbing ----

def test_vision_observation_reaches_the_filter():
    """`_on_vision` is the only path from the camera thread into the fused estimate."""
    bs = BaseStation()
    assert not bs.filter.initialised
    bs._on_vision(VisionObservation(t_mono=5.0, x_m=1.25, y_m=2.5, conf=0.8,
                                    method="monocular", track_id=3))
    assert bs.filter.initialised
    assert bs.filter.position == pytest.approx((1.25, 2.5))
    assert bs.freshness.last_t == pytest.approx(5.0)


def test_vision_uses_the_frame_timestamp_not_arrival_time():
    """Frames are timestamped at capture; inference latency must not look like freshness."""
    bs = BaseStation()
    bs._on_vision(VisionObservation(t_mono=123.0, x_m=1.0, y_m=1.0, conf=0.5,
                                    method="homography", track_id=1))
    assert bs.freshness.last_t == pytest.approx(123.0)


def test_drone_state_is_parsed_with_the_protocol_helper():
    """Task 4: main.py must not carry its own copy of the drone_state struct."""
    import kogane_base.main as main_mod
    from kogane_base.protocol import Frame, pack_drone_state

    assert not hasattr(main_mod, "_DRONE_STATE"), \
        "main.py should use protocol.unpack_drone_state, not a duplicate struct"

    bs = BaseStation()
    payload = pack_drone_state(150, -250, 100, 900, 11400, DS_F_POS_VALID, 90)
    bs._on_frame(Frame(MsgType.DRONE_STATE, 1, 0, payload), ("10.0.0.9", 5005))
    assert bs.drone_xy == pytest.approx((1.5, -2.5))
    assert bs._drone_addr == ("10.0.0.9", 5005)


def test_oversized_drone_state_payload_still_parses():
    """The old code sliced to size; keep tolerating trailing bytes."""
    from kogane_base.protocol import Frame, pack_drone_state

    bs = BaseStation()
    payload = pack_drone_state(100, 200, 0, 0, 11000, DS_F_POS_VALID, 90) + b"\xff\xff"
    bs._on_frame(Frame(MsgType.DRONE_STATE, 1, 0, payload), ("10.0.0.9", 5005))
    assert bs.drone_xy == pytest.approx((1.0, 2.0))


def test_short_drone_state_payload_is_ignored():
    from kogane_base.protocol import Frame

    bs = BaseStation()
    before = bs.drone_xy
    bs._on_frame(Frame(MsgType.DRONE_STATE, 1, 0, b"\x01\x02"), ("10.0.0.9", 5005))
    assert bs.drone_xy == before
    assert bs._drone_addr == ("10.0.0.9", 5005)     # address is still learned


def test_drone_state_does_not_count_as_a_target_measurement():
    """Telemetry from the drone says nothing about where the *person* is."""
    from kogane_base.protocol import Frame, pack_drone_state

    bs = BaseStation()
    bs._on_frame(Frame(MsgType.DRONE_STATE, 1, 0,
                       pack_drone_state(0, 0, 0, 0, 11000, 0, 90)), ("1.2.3.4", 5005))
    assert bs.freshness.last_t is None
    assert not bs.filter.initialised


def test_mmwave_frame_updates_filter_and_freshness():
    import struct

    from kogane_base.protocol import Frame

    bs = BaseStation()
    payload = bytes([1]) + struct.pack("<hhhH", 1000, 2000, 0, 100)
    bs._on_frame(Frame(MsgType.MMWAVE_TARGETS, 1, 0, payload), ("1.2.3.4", 5005))
    assert bs.filter.initialised
    assert bs.freshness.last_t is not None


def test_empty_mmwave_frame_does_not_mark_freshness():
    from kogane_base.protocol import Frame

    bs = BaseStation()
    bs._on_frame(Frame(MsgType.MMWAVE_TARGETS, 1, 0, bytes([0])), ("1.2.3.4", 5005))
    assert bs.freshness.last_t is None
    assert not bs.filter.initialised


def test_heartbeat_learns_the_drone_address_without_marking_freshness():
    from kogane_base.protocol import Frame, pack_heartbeat, Role

    bs = BaseStation()
    bs._on_frame(Frame(MsgType.HEARTBEAT, 1, 0, pack_heartbeat(1234, Role.DRONE)),
                 ("10.1.2.3", 5005))
    assert bs._drone_addr == ("10.1.2.3", 5005)
    assert bs.freshness.last_t is None
