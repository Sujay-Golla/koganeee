"""Bench-only Wi-Fi checks that never send a flight command.

Run from the base-station directory:
    python verify_wifi.py probe --host DRONE_IP
    python verify_wifi.py listen --seconds 10
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

from kogane_base.protocol import (
    DS_F_LINKQ_VALID,
    DS_F_YAW_VALID,
    DS_F_BATT_VALID,
    DS_F_FC_LINK_UP,
    DS_F_ARMED,
    MsgType,
    Role,
    pack,
    pack_heartbeat,
    unpack,
    unpack_drone_state,
    unpack_heartbeat,
)


def probe(host: str, port: int) -> None:
    # Valid framing with deliberately bad CRC: rejected before any dispatch.
    frame = bytearray(pack(MsgType.HEARTBEAT, pack_heartbeat(0, Role.BASE)))
    frame[-1] ^= 0xFF
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for index in range(2):
            sock.sendto(frame, (host, port))
            print(f"Sent CRC probe {index + 1}/2 to {host}:{port}")
            if index == 0:
                time.sleep(5.2)  # ESP32 prints reject counters at most every 5 s.
    print("Check the ESP32 monitor for 'rx rejects: ... crc=2'.")


def describe_state(state) -> str:
    fc_up = bool(state.flags & DS_F_FC_LINK_UP)
    armed = ("ARMED" if state.flags & DS_F_ARMED else "DISARMED") if fc_up else "unknown"
    yaw = f"{state.yaw_cd / 100:+.2f} deg" if state.flags & DS_F_YAW_VALID else "unknown"
    battery = f"{state.batt_mv / 1000:.3f} V" if state.flags & DS_F_BATT_VALID else "unknown"
    link = str(state.link_q) if state.flags & DS_F_LINKQ_VALID else "unknown"
    return (f"FC={'UP' if fc_up else 'DOWN'} {armed} yaw={yaw} "
            f"battery={battery} wifi_q={link} flags=0x{state.flags:02x}")


def listen(port: int, seconds: float, require_fc: bool = False) -> int:
    counts = {MsgType.HEARTBEAT: 0, MsgType.DRONE_STATE: 0}
    deadline = time.monotonic() + seconds
    last_fc = None
    last_state_print = -float("inf")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        print(f"Listening on UDP/{port} for {seconds:g} s; no commands will be sent")
        while time.monotonic() < deadline:
            sock.settimeout(min(1.0, max(0.01, deadline - time.monotonic())))
            try:
                data, addr = sock.recvfrom(1500)
            except socket.timeout:
                continue
            frame = unpack(data)
            if frame is None:
                print(f"Ignored malformed frame from {addr[0]}")
                continue
            if frame.msg_type == MsgType.HEARTBEAT:
                heartbeat = unpack_heartbeat(frame.payload)
                if heartbeat is not None:
                    counts[MsgType.HEARTBEAT] += 1
                    print(f"{addr[0]} HEARTBEAT uptime={heartbeat.uptime_ms} ms role={heartbeat.role}")
            elif frame.msg_type == MsgType.DRONE_STATE:
                state = unpack_drone_state(frame.payload)
                if state is not None:
                    counts[MsgType.DRONE_STATE] += 1
                    now = time.monotonic()
                    if state.flags & DS_F_FC_LINK_UP and state.flags & DS_F_YAW_VALID:
                        last_fc = now
                    if now - last_state_print >= 0.9:
                        print(f"{addr[0]} DRONE_STATE {describe_state(state)}")
                        last_state_print = now
    print(f"Received {counts[MsgType.HEARTBEAT]} HEARTBEAT and "
          f"{counts[MsgType.DRONE_STATE]} DRONE_STATE frames")
    if require_fc:
        if last_fc is None or time.monotonic() - last_fc > 2.0:
            print("FAIL: no recent FC heading received over Wi-Fi")
            return 1
        print("PASS: recent FC heading received over Wi-Fi")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    probe_parser = sub.add_parser("probe", help="Check ESP32 UDP receive and CRC rejection")
    probe_parser.add_argument("--host", required=True, help="ESP32 DHCP IPv4 address")
    probe_parser.add_argument("--port", type=int, default=5005)
    listen_parser = sub.add_parser("listen", help="Receive telemetry without sending commands")
    listen_parser.add_argument("--port", type=int, default=5005)
    listen_parser.add_argument("--seconds", type=float, default=10)
    listen_parser.add_argument("--require-fc", action="store_true",
                               help="fail unless fresh FC heading reaches the laptop")
    args = parser.parse_args()
    if args.command == "probe":
        probe(args.host, args.port)
        return 0
    else:
        return listen(args.port, args.seconds, args.require_fc)


if __name__ == "__main__":
    sys.exit(main())
