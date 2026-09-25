"""Where a built payload goes.

The screen and audio senders are the first things in this codebase that need to emit KGN
datagrams from *two* very different places: the asyncio base station, which already owns a
bound `UdpEndpoint`, and the hand-run CLI tools, which must work with the base station not
running at all. Rather than write each sender twice, they build payloads and hand them to a
`FrameSink`.

Both sinks keep their own rolling `seq`, which is correct: the header `seq` is per-sender,
and a CLI tool is a different sender from the base station even when it targets the same
drone.
"""
from __future__ import annotations

import logging
import socket
from typing import Callable, Protocol, runtime_checkable

from ..protocol import pack
from .udp import UdpEndpoint

log = logging.getLogger("kogane.net.sink")


@runtime_checkable
class FrameSink(Protocol):
    """Anything that can put one KGN payload on the wire."""

    def send(self, msg_type: int, payload: bytes) -> None: ...


class SocketSink:
    """Blocking UDP socket to one peer. What the CLI tools use.

    Deliberately unconnected (`sendto`, not `connect`) so an ICMP port-unreachable from a
    drone that is not listening cannot kill subsequent sends — a screen or audio stream to
    a drone that is booting should keep going, not die on chunk two.
    """

    def __init__(self, host: str, port: int, src_id: int = 0,
                 recv: bool = False, bind_port: int | None = None) -> None:
        self.addr = (host, int(port))
        self.src_id = int(src_id)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bound_port: int | None = None
        if recv:
            # Only bound when the caller wants to *hear* the drone, because binding the KGN
            # port would otherwise collide with a base station running on this host.
            #
            # The bind port is the base station's own port, not the destination port. The
            # drone does not reply to whoever it heard from: wifi_udp.c sends every outbound
            # frame to a configured CONFIG_KGN_BASE_IP:CONFIG_KGN_UDP_PORT. So AUDIO_MIC
            # arrives on the KGN port regardless of which source port asked for it. In a
            # normal run both numbers are 5005 and this distinction is invisible; it only
            # matters when talking to something on a non-standard port.
            self.bound_port = int(bind_port) if bind_port is not None else self.addr[1]
            self._sock.bind(("0.0.0.0", self.bound_port))
        self._seq = 0
        self.sent = 0
        self.sent_bytes = 0

    @property
    def sock(self) -> socket.socket:
        return self._sock

    def send(self, msg_type: int, payload: bytes) -> None:
        self._seq = (self._seq + 1) & 0xFFFF
        datagram = pack(msg_type, payload, self._seq, self.src_id)
        self._sock.sendto(datagram, self.addr)
        self.sent += 1
        self.sent_bytes += len(datagram)

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "SocketSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class EndpointSink:
    """Adapter onto the base station's `UdpEndpoint`.

    `addr` may be a callable so the sink follows the drone address the base station learns
    from HEARTBEAT/DRONE_STATE instead of freezing whatever it was at construction time.
    """

    def __init__(self, endpoint: UdpEndpoint,
                 addr: tuple[str, int] | Callable[[], tuple[str, int]],
                 src_id: int = 0) -> None:
        self._endpoint = endpoint
        self._addr = addr
        self.src_id = int(src_id)
        self.sent = 0

    @property
    def addr(self) -> tuple[str, int]:
        return self._addr() if callable(self._addr) else self._addr

    def send(self, msg_type: int, payload: bytes) -> None:
        self._endpoint.send(msg_type, payload, self.addr, self.src_id)
        self.sent += 1


class ListSink:
    """Collects payloads instead of sending them. For tests and `--dry-run`."""

    def __init__(self) -> None:
        self.frames: list[tuple[int, bytes]] = []

    def send(self, msg_type: int, payload: bytes) -> None:
        self.frames.append((int(msg_type), bytes(payload)))

    def payloads(self, msg_type: int | None = None) -> list[bytes]:
        return [p for t, p in self.frames if msg_type is None or t == int(msg_type)]

    def clear(self) -> None:
        self.frames.clear()
