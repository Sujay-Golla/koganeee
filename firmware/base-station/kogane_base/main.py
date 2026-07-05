"""Kogane base-station orchestrator.

Wires: UDP endpoint <- mmWave nodes / drone; Kalman fusion; setpoint P-loop -> drone;
voice + screen background tasks. Run with `python -m kogane_base`.
"""
from __future__ import annotations

import asyncio
import logging
import struct

from .config import CONFIG
from .fusion.kalman import PositionFilter
from .link.setpoint import compute_setpoint, SETPOINT_MSG
from .net.udp import UdpEndpoint
from .protocol import Frame, MsgType
from .screen.renderer import ScreenRenderer
from .tracking.mmwave import detections_from_payload
from .voice.pipeline import VoicePipeline

log = logging.getLogger("kogane.main")

# drone_state payload: x_cm, y_cm, z_cm, yaw_cd, batt_mv, flags, link_q
_DRONE_STATE = struct.Struct("<hhhhHBB")


class BaseStation:
    def __init__(self) -> None:
        self.filter = PositionFilter()
        self.udp = UdpEndpoint(CONFIG.udp_port, self._on_frame)
        self.voice = VoicePipeline()
        self.screen = ScreenRenderer()
        self.drone_xy = (CONFIG.room_w_m / 2, CONFIG.room_l_m / 2)  # until telemetry arrives
        self._drone_addr: tuple[str, int] = (CONFIG.drone_ip, CONFIG.udp_port)

    def _on_frame(self, frame: Frame, addr: tuple[str, int]) -> None:
        if frame.msg_type == MsgType.MMWAVE_TARGETS:
            dets = detections_from_payload(frame.src_id, frame.payload)
            if dets:
                d = dets[0]  # TODO(kogane): identity selection when >1 target
                self.filter.update(d.x_m, d.y_m)
        elif frame.msg_type == MsgType.DRONE_STATE:
            if len(frame.payload) >= _DRONE_STATE.size:
                x, y, _z, _yaw, _mv, _fl, _lq = _DRONE_STATE.unpack(
                    frame.payload[:_DRONE_STATE.size])
                self.drone_xy = (x / 100.0, y / 100.0)
            self._drone_addr = addr  # learn the drone's real address
        elif frame.msg_type == MsgType.HEARTBEAT:
            self._drone_addr = addr

    async def _control_loop(self) -> None:
        dt = 1.0 / CONFIG.loop_hz
        while True:
            self.filter.predict(dt)
            if self.filter._init:
                sp = compute_setpoint(self.drone_xy, self.filter.position)
                self.udp.send(SETPOINT_MSG, sp, self._drone_addr)
            await asyncio.sleep(dt)

    async def run(self) -> None:
        await self.udp.start()
        log.info("base station up on udp/%d, drone=%s", CONFIG.udp_port, CONFIG.drone_ip)
        await asyncio.gather(
            self._control_loop(),
            self.voice.run(),
            self.screen.run(),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(BaseStation().run())
    except KeyboardInterrupt:
        log.info("shutdown")


if __name__ == "__main__":
    main()
