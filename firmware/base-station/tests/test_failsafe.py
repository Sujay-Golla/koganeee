"""The staleness state machine that decides VELOCITY vs HOLD.

This is the safety-critical bit: the drone's failsafe is DROP, so commanding velocity
from a dead-reckoned estimate is worse than commanding nothing. Timestamps are supplied
by hand, so the tests are deterministic and need no sleeping, camera or network.
"""
from __future__ import annotations

import pytest

from kogane_base.fusion.kalman import PositionFilter
from kogane_base.link.failsafe import Freshness, StalenessMonitor


def test_starts_stale_with_no_measurement():
    m = StalenessMonitor(1.0)
    assert m.stale is True
    assert m.fresh(0.0) is False
    assert m.age(0.0) is None


def test_no_spurious_lost_transition_before_first_measurement():
    """Startup must not log 'target lost' — there was never a target."""
    m = StalenessMonitor(1.0)
    for t in (0.0, 0.5, 5.0, 100.0):
        assert m.poll(t) is None


def test_first_measurement_reports_acquired_once():
    m = StalenessMonitor(1.0)
    m.mark(10.0)
    assert m.poll(10.0) is Freshness.ACQUIRED
    assert m.poll(10.1) is None          # level, not edge: no repeat
    assert m.poll(10.2) is None


def test_fresh_inside_the_window_stale_outside():
    m = StalenessMonitor(1.0)
    m.mark(100.0)
    assert m.fresh(100.0) is True
    assert m.fresh(100.999) is True
    assert m.fresh(101.0) is True        # boundary is inclusive
    assert m.fresh(101.001) is False


def test_age_tracks_the_newest_measurement():
    m = StalenessMonitor(2.0)
    m.mark(50.0)
    assert m.age(50.75) == pytest.approx(0.75)
    m.mark(51.0)
    assert m.age(51.25) == pytest.approx(0.25)


def test_lost_transition_fires_exactly_once():
    m = StalenessMonitor(1.0)
    m.mark(0.0)
    m.poll(0.0)                                      # ACQUIRED
    assert m.poll(0.5) is None
    assert m.poll(1.5) is Freshness.LOST
    # the caller polls at 30 Hz; it must not be told again
    for i in range(30):
        assert m.poll(1.5 + 0.033 * (i + 1)) is None
    assert m.stale is True


def test_reacquire_after_loss_reports_acquired_again():
    m = StalenessMonitor(1.0)
    m.mark(0.0)
    assert m.poll(0.0) is Freshness.ACQUIRED
    assert m.poll(2.0) is Freshness.LOST
    m.mark(2.1)
    assert m.poll(2.1) is Freshness.ACQUIRED
    assert m.poll(2.2) is None


def test_full_acquire_lose_reacquire_cycle():
    m = StalenessMonitor(0.5)
    seen = []
    t = 0.0
    # 10 frames of good tracking at 30 Hz
    for _ in range(10):
        m.mark(t)
        seen.append(m.poll(t))
        t += 1 / 30
    # then the camera drops out for a second
    for _ in range(30):
        seen.append(m.poll(t))
        t += 1 / 30
    # then it comes back
    for _ in range(10):
        m.mark(t)
        seen.append(m.poll(t))
        t += 1 / 30

    transitions = [s for s in seen if s is not None]
    assert transitions == [Freshness.ACQUIRED, Freshness.LOST, Freshness.ACQUIRED]


def test_out_of_order_timestamps_ignored():
    """Vision observations can arrive slightly behind a mmWave datagram."""
    m = StalenessMonitor(1.0)
    m.mark(100.0)
    m.mark(99.0)                       # late arrival from the other sensor
    assert m.last_t == pytest.approx(100.0)
    assert m.fresh(100.5) is True


def test_either_sensor_keeps_the_target_fresh():
    """mmWave alone, camera alone, or both — the monitor does not care which."""
    m = StalenessMonitor(0.2)
    t = 0.0
    m.mark(t)                          # mmWave
    m.poll(t)
    for i in range(20):                # only the camera from here on
        t += 0.1
        m.mark(t)
        assert m.poll(t) is None       # never goes stale
    assert m.fresh(t) is True


def test_timeout_must_be_positive():
    with pytest.raises(ValueError):
        StalenessMonitor(0.0)
    with pytest.raises(ValueError):
        StalenessMonitor(-1.0)


def test_reset_returns_to_the_startup_state():
    m = StalenessMonitor(1.0)
    m.mark(5.0)
    m.poll(5.0)
    m.reset()
    assert m.stale is True
    assert m.last_t is None
    assert m.poll(6.0) is None


# ---- the public accessor that replaced main.py's `filter._init` ----

def test_filter_reports_uninitialised_before_any_measurement():
    f = PositionFilter()
    assert f.initialised is False


def test_filter_initialised_after_first_update():
    f = PositionFilter()
    f.update(1.0, 2.0)
    assert f.initialised is True
    assert f.position == pytest.approx((1.0, 2.0))


def test_initialised_agrees_with_the_legacy_private_flag():
    """`_init` is kept as the backing attribute so nothing else breaks."""
    f = PositionFilter()
    assert f.initialised is f._init
    f.update(0.0, 0.0)
    assert f.initialised is f._init is True


def test_predict_is_a_noop_before_initialisation():
    f = PositionFilter()
    f.predict(0.033)
    assert f.initialised is False
    assert f.position == pytest.approx((0.0, 0.0))


def test_filter_dead_reckons_which_is_why_staleness_exists():
    """Demonstrates the hazard the monitor guards against."""
    f = PositionFilter()
    f.update(0.0, 0.0)
    f.update(1.0, 0.0)                 # moving in +x
    for _ in range(300):               # 10 s at 30 Hz with no new measurement
        f.predict(1 / 30)
    # the filter still hands back a confident position, unbacked by any measurement
    assert f.initialised is True
    assert all(abs(v) < 1e9 for v in f.position)
