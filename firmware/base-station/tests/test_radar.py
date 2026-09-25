"""Tests for the LD2450 serial reader.

No serial port is opened and no radar exists: `RadarWorker._import_serial` is replaced with
a fake pyserial module, so the real open/read/close/retry logic runs against scripted bytes.
What is *not* covered here is pyserial's own behaviour on a physical adapter — whether an
unplug surfaces as `SerialException`, `OSError` or a silent stream of empty reads is
platform-specific, which is why the read loop treats all three as recoverable.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys

import pytest

from kogane_base.config import CONFIG
from kogane_base.main import BaseStation
from kogane_base.tracking import radar as radar_mod
from kogane_base.tracking.ld2450 import Target, encode_report
from kogane_base.tracking.radar import RadarObservation, RadarWorker


# ---- fakes -----------------------------------------------------------------
class FakeSerial:
    """Scripted `serial.Serial`. Each `read()` pops one chunk; then it reports timeouts."""

    def __init__(self, chunks, on_exhausted=None, read_error=None,
                 error_after: int = 0) -> None:
        self.chunks = list(chunks)
        self.closed = False
        self.reads = 0
        self._on_exhausted = on_exhausted
        self._read_error = read_error
        self._error_after = error_after

    def read(self, _n: int) -> bytes:
        self.reads += 1
        if self._read_error is not None and self.reads > self._error_after:
            raise self._read_error
        if self.chunks:
            return self.chunks.pop(0)
        if self._on_exhausted is not None:
            self._on_exhausted()
        return b""                      # read timeout, exactly like pyserial

    def close(self) -> None:
        self.closed = True


class FakeSerialModule:
    def __init__(self, factory) -> None:
        self._factory = factory
        self.opens: list[tuple[str, int, float]] = []
        self.instances: list[FakeSerial] = []

    def serial_for_url(self, url, baudrate, timeout):
        self.opens.append((url, baudrate, timeout))
        ser = self._factory()
        if isinstance(ser, FakeSerial):
            self.instances.append(ser)
        return ser


class ExplodingSerialModule(FakeSerialModule):
    def __init__(self, error: Exception) -> None:
        super().__init__(lambda: None)
        self._error = error

    def serial_for_url(self, url, baudrate, timeout):
        self.opens.append((url, baudrate, timeout))
        raise self._error


def cfg(**over):
    base = dict(radar_enabled=True, radar_port="COM_TEST", radar_baud=256000,
                radar_node_id=0)
    base.update(over)
    return dataclasses.replace(CONFIG, **base)


def run_worker(worker: RadarWorker, timeout: float = 10.0) -> None:
    """Drive `worker.run()` to completion and flush the cross-thread callbacks."""
    async def go():
        await asyncio.wait_for(worker.run(), timeout)
        for _ in range(3):
            await asyncio.sleep(0)      # let queued call_soon_threadsafe callbacks land
    asyncio.run(go())


def drive(monkeypatch, chunks, *, conf=None, read_error=None, error_after=0,
          stop_when_exhausted=True):
    """Run a worker over `chunks`, returning (worker, observations, fake module)."""
    obs: list[RadarObservation] = []
    worker = RadarWorker(on_observation=obs.append, cfg=conf or cfg())

    def factory():
        return FakeSerial(chunks, on_exhausted=worker.stop if stop_when_exhausted else None,
                          read_error=read_error, error_after=error_after)

    fake = FakeSerialModule(factory)
    monkeypatch.setattr(worker, "_import_serial", lambda: fake)
    run_worker(worker)
    return worker, obs, fake


def frame_at(x_mm: int, y_mm: int, speed_cms: int = 0, res_mm: int = 100) -> bytes:
    return encode_report([Target(x_mm, y_mm, speed_cms, res_mm)])


# ---- inert unless enabled -------------------------------------------------
def test_disabled_worker_never_touches_pyserial():
    worker = RadarWorker(cfg=cfg(radar_enabled=False))

    def boom():
        raise AssertionError("pyserial must not be imported when the radar is off")

    worker._import_serial = boom
    run_worker(worker)
    assert worker.frames_seen == 0
    assert not worker.active


def test_base_station_constructs_a_radar_worker_without_starting_it():
    bs = BaseStation()
    assert isinstance(bs.radar, RadarWorker)
    assert bs.radar.frames_seen == 0


# ---- happy path ----------------------------------------------------------
def test_one_frame_becomes_one_room_frame_observation(monkeypatch):
    # Node 0 sits at (0, 0) with yaw 45 deg, so a target 1414 mm straight ahead of the
    # sensor lands at room (-1.0, 1.0).
    worker, obs, _ = drive(monkeypatch, [frame_at(0, 1414, 50)])
    assert worker.frames_seen == 1
    assert len(obs) == 1
    det = obs[0].detections[0]
    assert (det.x_m, det.y_m) == pytest.approx((-1.0, 1.0), abs=1e-3)
    assert det.node_id == 0


def test_speed_is_reported_in_metres_per_second(monkeypatch):
    _worker, obs, _ = drive(monkeypatch, [frame_at(500, 1000, -45)])
    assert obs[0].detections[0].speed_ms == pytest.approx(-0.45)


def test_node_id_tags_the_detection_and_picks_the_pose(monkeypatch):
    # Node 1 is at (4, 5) with yaw 225 deg: a target 1 m ahead lands at (4.707, 4.293).
    _worker, obs, _ = drive(monkeypatch, [frame_at(0, 1000)], conf=cfg(radar_node_id=1))
    det = obs[0].detections[0]
    assert det.node_id == 1
    assert (det.x_m, det.y_m) == pytest.approx((4.7071, 4.2929), abs=1e-3)


def test_frames_split_across_reads_produce_one_observation(monkeypatch):
    f = frame_at(1000, 2000, 10)
    _worker, obs, _ = drive(monkeypatch, [f[:5], f[5:17], f[17:]])
    assert len(obs) == 1


def test_multiple_frames_in_one_read(monkeypatch):
    _worker, obs, _ = drive(monkeypatch, [frame_at(100, 1000) + frame_at(200, 2000)])
    assert len(obs) == 2


def test_empty_reports_do_not_emit_but_are_counted(monkeypatch):
    worker, obs, _ = drive(monkeypatch, [encode_report([])])
    assert worker.frames_seen == 1
    assert worker.targets_seen == 0
    assert obs == []


def test_a_target_on_the_sensor_origin_is_skipped(monkeypatch):
    """Matches detections_from_payload: x == y == 0 is not a usable fix."""
    worker, obs, _ = drive(monkeypatch, [frame_at(0, 0, 50)])
    assert worker.frames_seen == 1
    assert obs == []


def test_port_and_baud_come_from_config(monkeypatch):
    _worker, _obs, fake = drive(monkeypatch, [frame_at(1, 1000)],
                               conf=cfg(radar_port="/dev/ttyUSB7", radar_baud=115200))
    assert fake.opens[0][0] == "/dev/ttyUSB7"
    assert fake.opens[0][1] == 115200
    assert fake.opens[0][2] == pytest.approx(radar_mod._READ_TIMEOUT_S)


def test_the_port_is_closed_on_the_way_out(monkeypatch):
    _worker, _obs, fake = drive(monkeypatch, [frame_at(1, 1000)])
    assert fake.instances[0].closed


# ---- degradation ---------------------------------------------------------
def test_missing_pyserial_degrades_to_radar_off(monkeypatch):
    """`import serial` raising must not take the base station down."""
    monkeypatch.setitem(sys.modules, "serial", None)   # makes `import serial` raise
    worker = RadarWorker(cfg=cfg())
    run_worker(worker)
    assert worker.frames_seen == 0
    assert worker.last_error is not None
    assert "pyserial" in worker.last_error


def test_no_port_configured_does_not_attempt_an_open(monkeypatch):
    obs: list[RadarObservation] = []
    worker = RadarWorker(on_observation=obs.append, cfg=cfg(radar_port=""))
    fake = FakeSerialModule(lambda: FakeSerial([]))
    monkeypatch.setattr(worker, "_import_serial", lambda: fake)
    run_worker(worker)
    assert fake.opens == []
    assert worker.last_error == "no serial port configured"


def test_whitespace_only_port_is_treated_as_unconfigured(monkeypatch):
    worker = RadarWorker(cfg=cfg(radar_port="   "))
    fake = FakeSerialModule(lambda: FakeSerial([]))
    monkeypatch.setattr(worker, "_import_serial", lambda: fake)
    run_worker(worker)
    assert fake.opens == []


def test_busy_or_missing_port_retries_with_bounded_backoff_then_gives_up(monkeypatch):
    monkeypatch.setattr(radar_mod, "_OPEN_BACKOFF_S", 0.0)
    monkeypatch.setattr(radar_mod, "_MAX_BACKOFF_S", 0.0)
    worker = RadarWorker(cfg=cfg())
    fake = ExplodingSerialModule(OSError("could not open port: Access is denied"))
    monkeypatch.setattr(worker, "_import_serial", lambda: fake)
    run_worker(worker)
    assert len(fake.opens) == radar_mod._OPEN_RETRIES     # bounded, not infinite
    assert worker.last_error is not None
    assert "Access is denied" in worker.last_error


def test_unplug_mid_run_reopens_a_bounded_number_of_times(monkeypatch):
    monkeypatch.setattr(radar_mod, "_OPEN_BACKOFF_S", 0.0)
    monkeypatch.setattr(radar_mod, "_MAX_BACKOFF_S", 0.0)
    monkeypatch.setattr(radar_mod, "_READ_FAIL_LIMIT", 3)
    monkeypatch.setattr(radar_mod, "_REOPEN_LIMIT", 2)

    worker, obs, fake = drive(
        monkeypatch, [frame_at(500, 1500)],
        read_error=OSError("device reports readiness to read but returned no data"),
        error_after=1, stop_when_exhausted=False)

    # one initial open plus _REOPEN_LIMIT reopens, then it gives up
    assert len(fake.opens) == 3
    # every port that opened delivered its scripted frame before dying, and each of those
    # frames was still used rather than being lost with the port
    assert len(obs) == len(fake.instances) == 3
    assert all(inst.closed for inst in fake.instances)
    assert worker.last_error is not None


def test_pure_garbage_emits_nothing_and_does_not_raise(monkeypatch):
    noise = bytes(range(256)) * 8
    worker, obs, _ = drive(monkeypatch, [noise[i:i + 64] for i in range(0, len(noise), 64)])
    assert obs == []
    assert worker.frames_seen == 0


def test_garbage_then_a_real_frame_still_locks_on(monkeypatch):
    _worker, obs, _ = drive(monkeypatch, [b"\xaa\xff\x03\x00noise", frame_at(300, 1200)])
    assert len(obs) == 1


def test_stop_ends_the_read_loop_even_with_bytes_available(monkeypatch):
    """A never-ending stream must still shut down when asked."""
    obs: list[RadarObservation] = []
    worker = RadarWorker(on_observation=obs.append, cfg=cfg())
    f = frame_at(400, 1600)
    fake = FakeSerialModule(lambda: FakeSerial([f] * 10_000, on_exhausted=None))
    monkeypatch.setattr(worker, "_import_serial", lambda: fake)

    async def go():
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.05)
        worker.stop()
        await asyncio.wait_for(task, 5.0)

    asyncio.run(go())
    assert worker.frames_seen > 0
    assert fake.instances[0].closed


def test_emit_is_a_no_op_without_a_running_loop():
    """Guards the thread->loop handoff; `_emit` must not raise during shutdown."""
    worker = RadarWorker(on_observation=lambda o: (_ for _ in ()).throw(AssertionError))
    worker._emit(RadarObservation(t_mono=0.0, detections=[]))   # no loop set yet


# ---- into the base station ----------------------------------------------
def test_on_radar_updates_the_filter_and_freshness():
    from kogane_base.tracking.mmwave import Detection

    bs = BaseStation()
    assert not bs.filter.initialised
    bs._on_radar(RadarObservation(t_mono=42.0,
                                  detections=[Detection(1.5, 2.5, 0.3, 0)]))
    assert bs.filter.initialised
    assert bs.filter.position == pytest.approx((1.5, 2.5))
    assert bs.freshness.last_t == pytest.approx(42.0)


def test_on_radar_with_no_detections_does_not_mark_freshness():
    bs = BaseStation()
    bs._on_radar(RadarObservation(t_mono=42.0, detections=[]))
    assert bs.freshness.last_t is None
    assert not bs.filter.initialised


def test_run_launches_the_radar_task_and_stops_it_in_finally(monkeypatch):
    """Task 4: the radar joins the gather and is torn down like the vision worker."""
    bs = BaseStation()
    events: list[str] = []

    async def noop():
        return None

    async def radar_run():
        events.append("radar.run")

    monkeypatch.setattr(bs.udp, "start", noop)
    monkeypatch.setattr(bs, "_control_loop", noop)
    monkeypatch.setattr(bs.vision, "run", noop)
    monkeypatch.setattr(bs.voice, "run", noop)
    monkeypatch.setattr(bs.screen, "run", noop)
    monkeypatch.setattr(bs.radar, "run", radar_run)
    monkeypatch.setattr(bs.radar, "stop", lambda: events.append("radar.stop"))
    monkeypatch.setattr(bs.vision, "stop", lambda: events.append("vision.stop"))

    asyncio.run(bs.run())
    assert events == ["radar.run", "vision.stop", "radar.stop"]
