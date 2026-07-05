"""Asyncio UDP endpoint for KGN datagrams."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from ..protocol import Frame, pack, unpack

log = logging.getLogger("kogane.net")

FrameHandler = Callable[[Frame, tuple[str, int]], None]


class KgnProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_frame: FrameHandler) -> None:
        self._on_frame = on_frame
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport
        log.info("UDP endpoint ready")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        frame = unpack(data)
        if frame is None:
            log.debug("dropped malformed datagram from %s", addr)
            return
        self._on_frame(frame, addr)


class UdpEndpoint:
    """Bind a UDP socket; receive KGN frames and send back to peers."""

    def __init__(self, port: int, on_frame: FrameHandler) -> None:
        self._port = port
        self._on_frame = on_frame
        self._transport: asyncio.DatagramTransport | None = None
        self._seq = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: KgnProtocol(self._on_frame),
            local_addr=("0.0.0.0", self._port),
        )

    def send(self, msg_type: int, payload: bytes, addr: tuple[str, int], src_id: int = 0) -> None:
        if self._transport is None:
            return
        self._seq = (self._seq + 1) & 0xFFFF
        self._transport.sendto(pack(msg_type, payload, self._seq, src_id), addr)

    def close(self) -> None:
        if self._transport:
            self._transport.close()
