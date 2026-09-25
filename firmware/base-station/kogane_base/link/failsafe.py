"""Measurement-freshness tracking for the control loop.

The Kalman filter will dead-reckon indefinitely: once seeded it keeps producing a
plausible-looking position from pure extrapolation long after the last real detection.
That is fine for smoothing a one-frame dropout and actively dangerous over seconds,
because the drone's own failsafe is DROP — so a confidently wrong setpoint is worse than
no setpoint at all.

This is the state machine that decides whether the estimate is still backed by a real
measurement. It is a pure function of timestamps, no I/O, so it is unit-tested directly.
"""
from __future__ import annotations

from enum import Enum


class Freshness(Enum):
    """Transition reported by `StalenessMonitor.poll`."""
    ACQUIRED = "acquired"   # stale -> fresh: we have a real target again
    LOST = "lost"           # fresh -> stale: measurements dried up


class StalenessMonitor:
    """Tracks the newest measurement time and reports edges, not levels.

    `poll` returning a transition only on change is what lets the caller log once per
    event instead of 30 times a second.

    Starts in the stale state, so the very first measurement reports ACQUIRED and
    startup never reports a spurious LOST.
    """

    def __init__(self, timeout_s: float) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.timeout_s = float(timeout_s)
        self.last_t: float | None = None
        self._stale = True

    def mark(self, t_mono: float) -> None:
        """Record a real measurement at monotonic time `t_mono`.

        Out-of-order timestamps are ignored: observations can arrive from the vision
        thread slightly behind a mmWave datagram, and the newest is what matters.
        """
        if self.last_t is None or t_mono > self.last_t:
            self.last_t = float(t_mono)

    def age(self, now: float) -> float | None:
        """Seconds since the newest measurement, or None if there has never been one."""
        return None if self.last_t is None else now - self.last_t

    def fresh(self, now: float) -> bool:
        """True while the newest measurement is inside the timeout window."""
        age = self.age(now)
        return age is not None and age <= self.timeout_s

    def poll(self, now: float) -> Freshness | None:
        """Advance the state machine. Returns a transition on change, else None."""
        is_fresh = self.fresh(now)
        if is_fresh and self._stale:
            self._stale = False
            return Freshness.ACQUIRED
        if not is_fresh and not self._stale:
            self._stale = True
            return Freshness.LOST
        return None

    @property
    def stale(self) -> bool:
        """Last polled state. Use `fresh(now)` when you need it evaluated right now."""
        return self._stale

    def reset(self) -> None:
        self.last_t = None
        self._stale = True
