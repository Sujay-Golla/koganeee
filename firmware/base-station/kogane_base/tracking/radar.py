"""Bridge a directly-attached HLK-LD2450 into the asyncio base station.

Why this exists: the BOM has one LD2450 and a 3.3 V USB-UART adapter, and no ESP32-C3. So
the radar hangs off the laptop's own USB port and the laptop parses its UART protocol —
there is no node firmware in the path. Detections end up in exactly the same place they
would have if they had arrived as a `MMWAVE_TARGETS` datagram: `PositionFilter.update` plus
`StalenessMonitor.mark`.

Threading model is copied from `vision/runner.py` on purpose, so the base station has one
concurrency story and not two. `serial.read()` blocks, so the read loop runs on a worker
thread via `asyncio.to_thread` and hands finished observations back with
`loop.call_soon_threadsafe`. The callback therefore executes on the event loop thread, the
same thread as `_control_loop` and `_on_frame`, so nothing needs locking.

Everything degrades instead of raising: pyserial not installed, no port configured, port
missing, port held by another process, device unplugged mid-run, wrong baud producing pure
noise. Any of those log clearly and leave the base station running without radar.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

from ..config import CONFIG
from .ld2450 import Ld2450Parser, Target
from .mmwave import Detection, node_frame_to_room

log = logging.getLogger("kogane.tracking.radar")

# Opening the port: retry a few times, backing off, then give up for this run.
_OPEN_RETRIES = 4
_OPEN_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 8.0
# A dead port is worth reopening (USB re-enumerates on replug) but not forever.
_REOPEN_LIMIT = 3

# Read sizing: one report is 30 bytes at ~10 Hz, so a 64-byte read with a 200 ms timeout
# returns promptly with one or two frames and never busy-spins.
_READ_CHUNK = 64
_READ_TIMEOUT_S = 0.2
_READ_FAIL_LIMIT = 30
# The LD2450 streams continuously, so prolonged silence means the link is wrong, not idle.
_QUIET_WARN_S = 3.0
_STATUS_LOG_S = 10.0


@dataclass
class RadarObservation:
    """One LD2450 report, already projected into the shared room frame."""

    t_mono: float
    detections: list[Detection]
    targets: list[Target] = field(default_factory=list)
    hz: float = 0.0


class RadarWorker:
    """Owns the serial port and the frame parser.

    Construct it always; it is inert unless `CONFIG.radar_enabled`. pyserial is imported
    inside the worker thread, so a run without the radar extra installed never touches it.
    """

    def __init__(self, on_observation=None, cfg=None) -> None:
        self.cfg = cfg or CONFIG
        self._cb = on_observation
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

        # observable state, for logs / the screen renderer
        self.active = False
        self.last_error: str | None = None
        self.frames_seen = 0          # report frames decoded, including empty ones
        self.targets_seen = 0         # reports that contained at least one target
        self.hz = 0.0

    # ---- lifecycle ----
    async def run(self) -> None:
        """Task body for `asyncio.gather`. Returns immediately when the radar is off."""
        if not self.cfg.radar_enabled:
            log.info("radar disabled (set KGN_RADAR=1 to enable) — no serial port opened")
            return
        self._loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(self._worker)
        except asyncio.CancelledError:
            # to_thread cannot be interrupted; ask the read loop to finish its current read.
            self._stop.set()
            raise
        finally:
            self.active = False
        log.info("radar task exited after %d frames (%d with targets)",
                 self.frames_seen, self.targets_seen)

    def stop(self) -> None:
        self._stop.set()

    # ---- thread -> event loop ----
    def _emit(self, obs: RadarObservation) -> None:
        if self._cb is None:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._cb, obs)
        except RuntimeError:
            pass  # loop shut down between the check and the call

    # ---- serial handling (inside the worker thread) ----
    def _import_serial(self):
        try:
            import serial  # noqa: PLC0415 — deliberately lazy, see class docstring

            return serial
        except Exception as e:
            self.last_error = f"pyserial unavailable: {e}"
            log.error("radar disabled — pyserial is not installed (%s). Install the radar "
                      "extra with `pip install -e .[radar]`.", e)
            return None

    def _port_hint(self) -> str:
        """Best-effort list of ports, so a wrong KGN_RADAR_PORT is one log line to fix."""
        try:
            from serial.tools import list_ports  # noqa: PLC0415

            names = [f"{p.device} ({p.description})" for p in list_ports.comports()]
        except Exception:
            return "unavailable"
        return ", ".join(names) if names else "none found"

    def _open_serial(self, serial_mod):
        """Open the configured port, retrying with backoff. None => give up on radar."""
        port = (self.cfg.radar_port or "").strip()
        if not port:
            self.last_error = "no serial port configured"
            log.error("radar enabled but no port configured — set KGN_RADAR_PORT. "
                      "Ports seen: %s", self._port_hint())
            return None

        backoff = _OPEN_BACKOFF_S
        for attempt in range(1, _OPEN_RETRIES + 1):
            if self._stop.is_set():
                return None
            try:
                # serial_for_url, not Serial: a bare device name ("COM5", "/dev/ttyUSB0")
                # behaves identically, and it additionally accepts pyserial's URL handlers
                # so the whole read path can be exercised without hardware —
                # KGN_RADAR_PORT="socket://127.0.0.1:5556" reads LD2450 frames from a TCP
                # feeder, "loop://" from an in-process loopback.
                ser = serial_mod.serial_for_url(port, baudrate=int(self.cfg.radar_baud),
                                                timeout=_READ_TIMEOUT_S)
                log.info("LD2450 open: %s @ %d baud, tagging detections as node %d "
                         "(pose %s)", port, self.cfg.radar_baud, self.cfg.radar_node_id,
                         self.cfg.node_poses.get(self.cfg.radar_node_id, "unmapped"))
                return ser
            except Exception as e:
                self.last_error = f"serial open failed: {e}"
                log.error("radar open attempt %d/%d failed (%s @ %d): %s. Ports seen: %s",
                          attempt, _OPEN_RETRIES, port, self.cfg.radar_baud, e,
                          self._port_hint())
                if attempt < _OPEN_RETRIES:
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF_S)
        log.error("giving up on the radar: could not open %s after %d attempts. The base "
                  "station continues without it.", port, _OPEN_RETRIES)
        return None

    # ---- the blocking loop ----
    def _worker(self) -> None:
        serial_mod = self._import_serial()
        if serial_mod is None:
            return

        reopens = 0
        while not self._stop.is_set():
            ser = self._open_serial(serial_mod)
            if ser is None:
                return
            try:
                self._read_loop(ser)
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
                self.active = False
            if self._stop.is_set():
                return
            reopens += 1
            if reopens > _REOPEN_LIMIT:
                log.error("radar giving up after %d reopen attempts; base station "
                          "continues without radar input", reopens)
                return
            log.warning("reopening the radar port (attempt %d/%d)", reopens, _REOPEN_LIMIT)
            self._stop.wait(_OPEN_BACKOFF_S)

    def _read_loop(self, ser) -> None:
        """Read/parse until stopped or the device stops answering."""
        parser = Ld2450Parser()
        read_fails = 0
        now = time.monotonic()
        last_data = now
        last_quiet_log = now
        last_status_log = now
        last_frame_t: float | None = None

        while not self._stop.is_set():
            try:
                chunk = ser.read(_READ_CHUNK)
            except Exception as e:
                # SerialException here is the normal signature of an unplugged adapter.
                read_fails += 1
                self.last_error = f"serial read failed: {e}"
                if read_fails == 1 or read_fails % 10 == 0:
                    log.warning("radar read failed (%d consecutive): %s", read_fails, e)
                if read_fails >= _READ_FAIL_LIMIT:
                    log.error("%d consecutive radar read failures — dropping the port",
                              read_fails)
                    return
                self._stop.wait(0.05)
                continue

            now = time.monotonic()
            if not chunk:
                # Read timeout. Not fatal (the port is still open) but the LD2450 should be
                # streaming, so say so instead of sitting silently.
                if (now - last_data > _QUIET_WARN_S
                        and now - last_quiet_log > _QUIET_WARN_S):
                    last_quiet_log = now
                    log.warning("no radar bytes for %.1fs — check wiring, and that the "
                                "baud rate is %d", now - last_data, self.cfg.radar_baud)
                continue

            read_fails = 0
            last_data = now
            self.active = True

            reports = parser.feed(chunk)
            if reports:
                # Rate is computed per *read*, not per frame: one read can complete several
                # frames and they all share this timestamp, so charging each of them a
                # separate dt would invent a rate an order of magnitude too high.
                if last_frame_t is not None:
                    inst = len(reports) / max(1e-3, now - last_frame_t)
                    self.hz = (0.9 * self.hz + 0.1 * inst) if self.hz else inst
                last_frame_t = now

            for targets in reports:
                self.frames_seen += 1
                dets = self._to_room(targets)
                if not dets:
                    continue          # empty report: radar is alive, nobody in the beam
                self.targets_seen += 1
                self._emit(RadarObservation(t_mono=now, detections=dets,
                                            targets=list(targets), hz=self.hz))

            if now - last_status_log > _STATUS_LOG_S:
                last_status_log = now
                self._log_status(parser)

    def _to_room(self, targets: list[Target]) -> list[Detection]:
        """Sensor-frame targets -> room-frame detections, same transform as the node path."""
        node_id = int(self.cfg.radar_node_id)
        dets: list[Detection] = []
        for t in targets:
            if t.x_mm == 0 and t.y_mm == 0:
                continue              # matches detections_from_payload's convention
            rx, ry = node_frame_to_room(node_id, t.x_mm, t.y_mm)
            dets.append(Detection(rx, ry, t.speed_cms / 100.0, node_id))
        return dets

    def _log_status(self, parser: Ld2450Parser) -> None:
        """Periodic one-liner. Bad footers with no frames means the baud rate is wrong."""
        if parser.frames_decoded == 0:
            log.warning("radar: bytes arriving but no valid frames (%d bad footers, "
                        "%d bytes discarded) — wrong baud rate or not an LD2450?",
                        parser.bad_footers, parser.bytes_discarded)
            return
        log.info("radar: %d frames, %d with targets, %.1f Hz, %d bad footers",
                 self.frames_seen, self.targets_seen, self.hz, parser.bad_footers)
