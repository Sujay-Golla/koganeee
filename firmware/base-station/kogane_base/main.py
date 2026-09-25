"""Kogane base-station orchestrator.

Wires: UDP endpoint <- mmWave nodes / drone; camera -> person tracking; Kalman fusion;
setpoint P-loop -> drone; voice + screen background tasks. Run with `python -m kogane_base`.

Threading model: everything except camera capture/inference and the LD2450 serial read runs
on the single asyncio event loop. Both of those block, so each runs its loop on a worker
thread and delivers results back onto the event loop (see vision/runner.py and
tracking/radar.py), which means `_on_vision`, `_on_radar`, `_on_frame` and `_control_loop`
all execute on the same thread and share state without locks.

Two mmWave paths converge here and both end at `PositionFilter.update` + `Freshness.mark`:
an ESP32-C3 node sending `MMWAVE_TARGETS` datagrams (`_on_frame`), and an LD2450 attached to
this laptop over USB-UART (`_on_radar`). The second is what the BOM actually has parts for.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .audio.recorder import MicRecorder
from .config import CONFIG
from .fusion.kalman import PositionFilter
from .link.failsafe import Freshness, StalenessMonitor
from .link.setpoint import compute_setpoint, SETPOINT_MSG
from .net.sink import EndpointSink
from .net.udp import UdpEndpoint
from .protocol import (CtrlMode, DRONE_STATE_LEN, DS_F_BATT_VALID, DS_F_LINKQ_VALID, Frame,
                       MsgType, pack_setpoint, unpack_drone_state)
from .screen.frames import ReadoutState
from .screen.renderer import ScreenRenderer
from .tracking.mmwave import detections_from_payload
from .tracking.radar import RadarWorker
from .vision.runner import VisionWorker
from .voice.pipeline import VoicePipeline

log = logging.getLogger("kogane.main")

# Guard against a pathological dt (host suspend, debugger breakpoint) blowing up the
# filter covariance. At 30 Hz a legitimate dt is ~33 ms.
_MAX_DT_S = 0.5

HOLD_SETPOINT = pack_setpoint(0, 0, 0, 0, CtrlMode.HOLD)


class BaseStation:
    def __init__(self) -> None:
        self.filter = PositionFilter()
        self.udp = UdpEndpoint(CONFIG.udp_port, self._on_frame)
        self.voice = VoicePipeline()
        self.vision = VisionWorker(on_observation=self._on_vision)
        self.radar = RadarWorker(on_observation=self._on_radar)
        # Fresh only while a real detection (mmWave or camera) has arrived recently.
        self.freshness = StalenessMonitor(CONFIG.target_stale_s)
        self.drone_xy = (CONFIG.room_w_m / 2, CONFIG.room_l_m / 2)  # until telemetry arrives
        self._drone_addr: tuple[str, int] = (CONFIG.drone_ip, CONFIG.udp_port)
        self._last_vision_log = 0.0
        self._last_radar_log = 0.0

        # Screen: the sink follows `_drone_addr` via a callable rather than freezing it, so
        # the panel updates start going to the real drone the moment a HEARTBEAT teaches us
        # its address. The renderer pulls a state snapshot instead of holding a reference to
        # `self`, which is what keeps it unit-testable.
        self.screen = ScreenRenderer(
            sink=EndpointSink(self.udp, lambda: self._drone_addr),
            state=self.screen_state,
        )

        # Inbound drone mic audio. Constructed unconditionally (it is a bytearray and a
        # counter) but it only ever fills if something sends CTRL MIC_ON — the drone boots
        # with streaming off.
        self.mic = MicRecorder()
        self._last_mic_log = 0.0

        # Recent target positions for the panel's plan view.
        self._trail: list[tuple[float, float]] = []
        self._identity: str | None = None
        self._link_q: int | None = None
        self._batt_mv: int | None = None

    # ---- inputs -------------------------------------------------------------------
    def _on_frame(self, frame: Frame, addr: tuple[str, int]) -> None:
        if frame.msg_type == MsgType.MMWAVE_TARGETS:
            dets = detections_from_payload(frame.src_id, frame.payload)
            if dets:
                d = dets[0]  # TODO(kogane): identity selection when >1 target
                self.filter.update(d.x_m, d.y_m)
                self.freshness.mark(time.monotonic())
        elif frame.msg_type == MsgType.DRONE_STATE:
            if len(frame.payload) >= DRONE_STATE_LEN:
                st = unpack_drone_state(frame.payload[:DRONE_STATE_LEN])
                if st is not None:
                    self.drone_xy = (st.x_cm / 100.0, st.y_cm / 100.0)
                    # Only for the panel readout, and only when the drone says the field is
                    # real: PROTOCOL.md is explicit that a clear validity bit means "no
                    # data", not a measurement of zero. Showing "LINK 0" when the drone
                    # never claimed to know would be inventing telemetry.
                    if st.flags & DS_F_LINKQ_VALID:
                        self._link_q = st.link_q
                    if st.flags & DS_F_BATT_VALID:
                        self._batt_mv = st.batt_mv
            self._drone_addr = addr  # learn the drone's real address
        elif frame.msg_type == MsgType.HEARTBEAT:
            self._drone_addr = addr
        elif frame.msg_type == MsgType.AUDIO_MIC:
            self._on_mic(frame, addr)

    def _on_mic(self, frame: Frame, addr: tuple[str, int]) -> None:
        """Inbound drone microphone audio (0x41).

        Nothing here starts the stream: the drone boots with the mic off and only begins on
        an `AUDIO_TTS fmt 2 cmd 1`. If chunks are arriving, something asked for them.
        """
        chunk = self.mic.on_payload(frame.payload)
        if chunk is None:
            return
        self._drone_addr = addr
        now = time.monotonic()
        if now - self._last_mic_log > 2.0:
            self._last_mic_log = now
            log.info("mic %.1fs buffered, seq=%d peak=%d (%s)",
                     self.mic.buffered_s, chunk.seq, self.mic.stats.peak,
                     self.mic.stats.describe())

    def _on_radar(self, obs) -> None:
        """Locally-attached LD2450 report, already in the room frame.

        Called via `loop.call_soon_threadsafe` from the radar thread, so this runs on the
        event loop thread. Identical treatment to a `MMWAVE_TARGETS` datagram in
        `_on_frame` — the only difference is that the bytes came off a serial port instead
        of off the network.
        """
        if not obs.detections:
            return
        d = obs.detections[0]  # TODO(kogane): identity selection when >1 target
        self.filter.update(d.x_m, d.y_m)
        self.freshness.mark(obs.t_mono)
        now = time.monotonic()
        if now - self._last_radar_log > 2.0:
            self._last_radar_log = now
            log.info("radar[node %d] %d target(s) xy=(%.2f, %.2f) v=%.2f m/s %.1f Hz",
                     d.node_id, len(obs.detections), d.x_m, d.y_m, d.speed_ms, obs.hz)

    def _on_vision(self, obs) -> None:
        """Camera observation, already projected into the room frame.

        Called via `loop.call_soon_threadsafe` from the vision thread, so this body runs
        on the event loop thread — same as the control loop.
        """
        self.filter.update(obs.x_m, obs.y_m)
        self.freshness.mark(obs.t_mono)
        now = time.monotonic()
        if now - self._last_vision_log > 2.0:
            self._last_vision_log = now
            log.info("cam[%s] id=%s%s xy=(%.2f, %.2f) %.1f fps gesture=%s",
                     obs.method, obs.track_id,
                     f" ({obs.identity})" if obs.identity else "",
                     obs.x_m, obs.y_m, obs.fps, obs.gesture)
        if obs.identity:
            self._identity = obs.identity
        if obs.beckon:
            # TODO(kogane): route this into the voice/mode state machine as "come here".
            log.info("gesture trigger: come-here from track %d", obs.track_id)

    # ---- panel ---------------------------------------------------------------------
    def screen_state(self) -> ReadoutState:
        """Snapshot of what the drone's panel should show right now.

        Called from the screen task; runs on the event loop thread like everything else, so
        it reads the same state the control loop just wrote with no locking. Fields the
        drone never told us stay None so the panel shows "--" instead of a made-up zero.
        """
        now = time.monotonic()
        fresh = self.freshness.fresh(now)
        target = self.filter.position if self.filter.initialised else None
        if target is not None and fresh:
            self._trail.append(target)
            del self._trail[:-48]
        return ReadoutState(
            target_xy=target,
            fresh=fresh,
            identity=self._identity if fresh else None,
            link_q=self._link_q,
            batt_mv=self._batt_mv,
            drone_xy=self.drone_xy,
            room=(CONFIG.room_w_m, CONFIG.room_l_m),
            trail=list(self._trail),
        )

    # ---- control ------------------------------------------------------------------
    async def _control_loop(self) -> None:
        period = 1.0 / CONFIG.loop_hz
        last = time.monotonic()
        while True:
            await asyncio.sleep(period)
            now = time.monotonic()
            dt = min(max(now - last, 1e-4), _MAX_DT_S)
            last = now

            self.filter.predict(dt)

            transition = self.freshness.poll(now)
            if transition is Freshness.LOST:
                log.warning("target lost (no measurement for >%.1fs) — holding",
                            CONFIG.target_stale_s)
            elif transition is Freshness.ACQUIRED:
                log.info("target acquired — following")

            if not self.filter.initialised:
                continue

            if self.freshness.fresh(now):
                sp = compute_setpoint(self.drone_xy, self.filter.position)
            else:
                # The filter is still extrapolating, but nothing real backs it. Keep the
                # link alive with HOLD rather than commanding a velocity into the void.
                sp = HOLD_SETPOINT
            self.udp.send(SETPOINT_MSG, sp, self._drone_addr)

    async def run(self) -> None:
        await self.udp.start()
        log.info("base station up on udp/%d, drone=%s, vision=%s, radar=%s, screen=%s, "
                 "stale_timeout=%.1fs",
                 CONFIG.udp_port, CONFIG.drone_ip,
                 "on" if CONFIG.vision_enabled else "off",
                 f"on ({CONFIG.radar_port or 'no port set'})" if CONFIG.radar_enabled
                 else "off",
                 f"on ({CONFIG.screen_mode})" if CONFIG.screen_enabled else "off",
                 CONFIG.target_stale_s)
        try:
            await asyncio.gather(
                self._control_loop(),
                self.radar.run(),
                self.vision.run(),
                self.voice.run(),
                self.screen.run(),
            )
        finally:
            self.vision.stop()
            self.radar.stop()
            self.screen.stop()
            # Only if KGN_MIC_WAV is set. No path, no file: a microphone on an aircraft
            # should not leave recordings behind because a process happened to exit.
            if CONFIG.mic_wav_path:
                try:
                    self.mic.write_wav()
                except Exception as e:                       # pragma: no cover
                    log.warning("could not write %s: %s", CONFIG.mic_wav_path, e)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(BaseStation().run())
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
