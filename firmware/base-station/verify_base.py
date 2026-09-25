"""Throwaway: run the real base station with the live panel readout on and watch it push.

Acts as the drone: sends one HEARTBEAT so the base learns this socket's address (exactly how
`_on_frame` discovers the real drone), feeds it a synthetic mmWave target so there is
something to display, then decodes the SCREEN_FRAME text rows that come back.
Deleted after the verification run.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time

BASE_PORT = 45021


def main() -> int:
    drone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    drone.bind(("127.0.0.1", 0))
    drone_port = drone.getsockname()[1]
    drone.settimeout(0.3)

    env = dict(os.environ)
    env.update({
        "KGN_UDP_PORT": str(BASE_PORT),
        "KGN_DRONE_IP": "127.0.0.1",
        "KGN_SCREEN": "1",
        "KGN_SCREEN_MODE": "text",
        "KGN_SCREEN_INTERVAL_S": "0.4",
    })
    proc = subprocess.Popen([sys.executable, "-m", "kogane_base"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    logs: list[str] = []
    threading.Thread(target=lambda: logs.extend(proc.stdout), daemon=True).start()

    from kogane_base import protocol as p
    from kogane_base.tools.mmwave_sim import build_datagram

    dest = ("127.0.0.1", BASE_PORT)
    try:
        time.sleep(1.5)
        # Teach the base where "the drone" is, the way a real HEARTBEAT does.
        drone.sendto(p.pack(p.MsgType.HEARTBEAT, p.pack_heartbeat(0, p.Role.DRONE)), dest)
        drone.sendto(p.pack(p.MsgType.DRONE_STATE,
                            p.pack_drone_state(120, 250, 150, 0, 11400,
                                               p.DS_F_LINKQ_VALID | p.DS_F_BATT_VALID, 88)),
                     dest)

        rows: dict[int, str] = {}
        setpoints = 0
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            drone.sendto(build_datagram(0, 2.0, 3.0, speed_cms=40), dest)
            time.sleep(0.1)
            while True:
                try:
                    data, _ = drone.recvfrom(2048)
                except OSError:
                    break
                f = p.unpack(data)
                if f is None:
                    continue
                if f.msg_type == int(p.MsgType.SETPOINT):
                    setpoints += 1
                elif f.msg_type == int(p.MsgType.SCREEN_FRAME):
                    line = p.unpack_screen_text(f.payload)
                    if line is not None:
                        rows[line.row] = line.text
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        drone.close()

    print("--- base station log ---")
    for line in logs:
        print("  " + line.rstrip())
    print("--- panel rows the drone would have rendered ---")
    for row in sorted(rows):
        print(f"  row {row}: {rows[row]!r}")
    print(f"--- {setpoints} SETPOINT datagram(s) still flowing while the panel updated")

    ok = bool(rows) and setpoints > 0 and "screen renderer started" in "".join(logs)
    print("BASE STATION SCREEN WIRING OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
