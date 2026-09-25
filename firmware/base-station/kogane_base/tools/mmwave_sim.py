"""Synthesise a walking person and send KGN `MMWAVE_TARGETS` datagrams to the base station.

This is how the fusion -> navigation -> setpoint chain becomes observable with no radar and
no drone on the bench, and it is the only thing that exercises `BaseStation._on_frame`'s
mmWave branch end to end over a real socket.

    # terminal 1
    python -m kogane_base
    # terminal 2
    kogane-mmwave-sim --path circle --rate 10 --fake-drone

The path is defined in **room** metres and then expressed in the sensor frame of
`--node-id` with `tracking.mmwave.room_to_node_frame`, so the base station's own transform
maps it straight back onto the intended room path. Get the pose in `CONFIG.node_poses`
wrong and you will see it: the drawn path lands somewhere else.

`--fake-drone` additionally pretends to be the drone: it sends one HEARTBEAT so the base
learns this socket's address (that is exactly how `_on_frame` discovers the real drone),
then prints the SETPOINT datagrams the base sends back. Without it the base keeps sending
setpoints to `KGN_DRONE_IP` and nothing here can see them.
"""
from __future__ import annotations

import argparse
import math
import random
import socket
import time

from ..config import CONFIG
from ..protocol import (MsgType, Role, pack, pack_heartbeat, pack_mmwave, unpack,
                        unpack_setpoint)
from ..tracking.mmwave import room_to_node_frame

# Plausible LD2450 distance-resolution reading; the base station ignores the field.
_DEFAULT_RES_MM = 100


# ---- paths: elapsed seconds -> (x_m, y_m) in the room frame ----------------------------
def _make_path(kind: str, cx: float, cy: float, speed: float, radius: float, length: float):
    if kind == "static":
        return lambda t: (cx, cy)

    if kind == "line":
        # Back and forth along room +x through the centre: a triangle wave on distance.
        half = length / 2.0
        period = 2.0 * length / speed if speed > 0 else 1.0

        def line(t: float) -> tuple[float, float]:
            phase = (t % period) / period            # 0..1
            offset = 4.0 * abs(phase - 0.5) - 1.0    # 1 -> -1 -> 1
            return cx + offset * half, cy
        return line

    if kind == "circle":
        w = speed / radius if radius > 0 else 0.0

        def circle(t: float) -> tuple[float, float]:
            return cx + radius * math.cos(w * t), cy + radius * math.sin(w * t)
        return circle

    if kind == "square":
        side = length
        perimeter = 4.0 * side

        def square(t: float) -> tuple[float, float]:
            s = (speed * t) % perimeter
            leg, along = divmod(s, side)
            h = side / 2.0
            if leg == 0:
                return cx - h + along, cy - h
            if leg == 1:
                return cx + h, cy - h + along
            if leg == 2:
                return cx + h - along, cy + h
            return cx - h, cy + h - along
        return square

    if kind == "figure8":
        # Lemniscate of Gerono. Speed is not constant along it; close enough for a demo.
        w = speed / radius if radius > 0 else 0.0

        def eight(t: float) -> tuple[float, float]:
            return cx + radius * math.sin(w * t), cy + radius * math.sin(w * t) * math.cos(w * t)
        return eight

    raise ValueError(f"unknown path {kind!r}")


def build_datagram(node_id: int, x_m: float, y_m: float, speed_cms: int = 0,
                   seq: int = 0, res_mm: int = _DEFAULT_RES_MM) -> bytes:
    """A complete KGN MMWAVE_TARGETS datagram placing one target at room (x_m, y_m).

    The room point is converted into `node_id`'s sensor frame first, so the base station's
    `node_frame_to_room` puts it back exactly where it was asked for. Split out from `main`
    so tests can drive `BaseStation._on_frame` with the real bytes this tool sends.
    """
    x_mm, y_mm = room_to_node_frame(node_id, x_m, y_m)
    payload = pack_mmwave([(x_mm, y_mm, int(speed_cms), int(res_mm))])
    return pack(MsgType.MMWAVE_TARGETS, payload, seq, src_id=node_id)


def _parse_xy(raw: str, default: tuple[float, float]) -> tuple[float, float]:
    if not raw:
        return default
    parts = [p for p in raw.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected 'x,y' in metres")
    return float(parts[0]), float(parts[1])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kogane-mmwave-sim",
        description="Emit synthetic KGN MMWAVE_TARGETS datagrams for a walking person.")
    ap.add_argument("--host", default="127.0.0.1", help="base station address")
    ap.add_argument("--port", type=int, default=CONFIG.udp_port, help="base station UDP port")
    ap.add_argument("--node-id", type=int, default=0,
                    help="src_id of the datagrams; picks the CONFIG.node_poses entry used")
    ap.add_argument("--path", default="circle",
                    choices=["static", "line", "circle", "square", "figure8"])
    ap.add_argument("--rate", type=float, default=10.0,
                    help="datagrams per second (the LD2450's own rate is ~10)")
    ap.add_argument("--speed", type=float, default=1.0, help="walking speed, m/s")
    ap.add_argument("--radius", type=float, default=1.0, help="circle/figure8 radius, m")
    ap.add_argument("--length", type=float, default=2.0, help="line length / square side, m")
    ap.add_argument("--center", default="",
                    help="path centre as 'x,y' in metres (default: room centre)")
    ap.add_argument("--jitter", type=float, default=0.02,
                    help="gaussian position noise, m (0 disables)")
    ap.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = run forever")
    ap.add_argument("--drop", type=float, default=0.0,
                    help="fraction of datagrams to drop, 0..1 — exercises the staleness "
                         "failsafe")
    ap.add_argument("--fake-drone", action="store_true",
                    help="also act as the drone: heartbeat once, then print returned "
                         "setpoints")
    ap.add_argument("--quiet", action="store_true", help="do not print each datagram")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rate <= 0:
        raise SystemExit("--rate must be positive")

    cx, cy = _parse_xy(args.center, (CONFIG.room_w_m / 2.0, CONFIG.room_l_m / 2.0))
    path = _make_path(args.path, cx, cy, args.speed, args.radius, args.length)
    dest = (args.host, args.port)
    period = 1.0 / args.rate

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.0)  # non-blocking; we poll for setpoints between sends
    try:
        if args.fake_drone:
            sock.sendto(pack(MsgType.HEARTBEAT, pack_heartbeat(0, Role.DRONE), 0,
                             src_id=0), dest)
            print(f"sent HEARTBEAT as the drone to {dest[0]}:{dest[1]} — the base will now "
                  f"address its setpoints here")

        print(f"mmwave-sim -> {dest[0]}:{dest[1]}  node={args.node_id} path={args.path} "
              f"rate={args.rate:g}Hz speed={args.speed:g}m/s centre=({cx:.2f}, {cy:.2f}) "
              f"pose={CONFIG.node_poses.get(args.node_id, 'unmapped')}")

        t0 = time.monotonic()
        seq = 0
        sent = 0
        dropped = 0
        setpoints = 0
        prev: tuple[float, float] | None = None
        prev_t = t0
        next_send = t0

        while True:
            now = time.monotonic()
            elapsed = now - t0
            if args.duration and elapsed >= args.duration:
                break

            x_m, y_m = path(elapsed)
            if args.jitter:
                x_m += random.gauss(0.0, args.jitter)
                y_m += random.gauss(0.0, args.jitter)

            # Finite-difference the path for a speed reading, the way the radar's own
            # Doppler figure would roughly behave. Sign is "closing on the sensor".
            speed_cms = 0
            if prev is not None:
                dt = max(1e-3, now - prev_t)
                speed_cms = int(round(
                    math.hypot(x_m - prev[0], y_m - prev[1]) / dt * 100.0))
            prev, prev_t = (x_m, y_m), now

            x_mm, y_mm = room_to_node_frame(args.node_id, x_m, y_m)
            seq = (seq + 1) & 0xFFFF

            if args.drop and random.random() < args.drop:
                dropped += 1
            else:
                sock.sendto(build_datagram(args.node_id, x_m, y_m, speed_cms, seq), dest)
                sent += 1
                if not args.quiet and sent % max(1, int(args.rate)) == 0:
                    print(f"t={elapsed:6.1f}s room=({x_m:5.2f}, {y_m:5.2f}) m  "
                          f"node=({x_mm:6d}, {y_mm:6d}) mm  v={speed_cms:4d} cm/s  "
                          f"sent={sent} dropped={dropped} setpoints={setpoints}")

            setpoints += _drain_setpoints(sock, quiet=args.quiet or not args.fake_drone)

            next_send += period
            sleep_for = next_send - time.monotonic()
            if sleep_for < -period:
                next_send = time.monotonic()      # we fell behind; resynchronise
            elif sleep_for > 0:
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        print()
    finally:
        sock.close()
    return 0


def _drain_setpoints(sock: socket.socket, quiet: bool) -> int:
    """Read whatever the base has sent back. Returns how many SETPOINTs were seen."""
    count = 0
    while True:
        try:
            data, _addr = sock.recvfrom(2048)
        except (BlockingIOError, socket.timeout):
            return count
        except OSError:
            return count
        frame = unpack(data)
        if frame is None or frame.msg_type != MsgType.SETPOINT:
            continue
        count += 1
        sp = unpack_setpoint(frame.payload)
        if sp is not None and not quiet and count == 1:
            print(f"    <- SETPOINT vx={sp.vx_cms:4d} vy={sp.vy_cms:4d} "
                  f"mode={sp.ctrl_mode}")
    return count


if __name__ == "__main__":
    raise SystemExit(main())
