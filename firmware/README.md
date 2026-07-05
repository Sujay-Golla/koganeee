# KOGANE — Firmware Workflow (Baseline)

> Baseline firmware/software workflow for the whole Kogane system.
> This is a **skeleton + workflow**, not a finished flight stack. Each target builds
> and has clearly marked `TODO` stubs where real logic goes.
>
> Read `hardware/DESIGN.md` (architecture + pin map) and `hardware/WIRING_GUIDE.md` first.

---

## 1. System at a glance

Kogane is a companion drone. Perception/voice/fusion run **off-board on a laptop**;
the drone only stabilizes itself and follows position/velocity setpoints.

```
                 Wi-Fi UDP                         MAVLink (telem) + MSP (override)
 LD2450 nodes ───────────────►  LAPTOP (base)  ───────────────►  ESP32-S3  ───UART1───►  F722 (iNAV)
 (ESP32-C3 x2)                  fusion+voice+UI     Wi-Fi UDP     companion              flight core
                                       ▲                             │
 drone OV2640 ──MJPEG/Wi-Fi────────────┘                 I2S audio / SPI LCD / servo
```

There are **four firmware/software targets** in this repo:

| Dir | Target | Toolchain | What it does |
|-----|--------|-----------|--------------|
| `fc-inav/` | STM32F722 flight core | iNAV 9.x (config, no C code) | rate/attitude stabilization, altitude hold (VL53L1X), DShot motors, RC+failsafe, blackbox |
| `companion-esp32s3/` | ESP32-S3-WROOM-1 | ESP-IDF | Wi-Fi/UDP link, FC bridge (MAVLink in / MSP override out), I2S audio, SPI display, OV2640 camera, servo |
| `mmwave-node-esp32c3/` | ESP32-C3 (x2) | ESP-IDF | read HLK-LD2450 over UART, forward targets as UDP to the laptop |
| `base-station/` | Laptop | Python 3.11+ | sensor fusion (Kalman), voice pipeline, setpoint sender, screen renderer |

Shared wire-protocol definitions live in [`shared/PROTOCOL.md`](shared/PROTOCOL.md).

The CubeMX file [`firmware.ioc`](firmware.ioc) is a **pinout reference only** — iNAV owns
clock/USB/peripheral config at runtime. Keep it in sync with `hardware/DESIGN.md §5`.

---

## 2. Protocols (who speaks what)

| Link | Transport | Protocol | Direction |
|------|-----------|----------|-----------|
| LD2450 node → laptop | Wi-Fi UDP | `KGN` datagram (see PROTOCOL.md) | node → base |
| laptop → drone ESP32 | Wi-Fi UDP | `KGN` datagram (setpoints, screen, audio) | base ↔ drone |
| drone OV2640 → laptop | Wi-Fi (HTTP/MJPEG) | MJPEG stream | drone → base |
| ESP32-S3 → F722 (telem) | UART1 @ 115200 | **MAVLink v2** (iNAV telemetry out) | FC → ESP32 |
| ESP32-S3 → F722 (control) | UART1 (shared) | **MSP v2 override** | ESP32 → FC |

> **iNAV reality check:** iNAV emits MAVLink *telemetry* but does **not** ingest MAVLink
> position/velocity commands. Autonomous setpoints are injected with **MSP RC override**
> (`MSP_SET_RAW_RC` / MSP override). So the companion parses MAVLink for state and sends
> MSP frames for control on the same UART. See `companion-esp32s3/main/link_fc.*`.

---

## 3. Per-target build & flash

### 3.1 `fc-inav/` (iNAV on the F722)
No compiler needed for the baseline — you flash a stock iNAV build and apply a CLI diff.
```powershell
# 1. Flash iNAV via DFU: hold BOOT, tap RESET, then in iNAV Configurator flash the
#    matching F722 target (see fc-inav/README.md for target selection).
# 2. Open the CLI tab and paste the config:
#    fc-inav/config/kogane-fc.diff
```
To build a **custom target** from iNAV source, see `fc-inav/README.md`.

### 3.2 `companion-esp32s3/` and `mmwave-node-esp32c3/` (ESP-IDF)
```powershell
# one-time: install ESP-IDF v5.x and run export.ps1 in each new shell
idf.py set-target esp32s3      # (esp32c3 for the node)
idf.py menuconfig              # set Wi-Fi SSID/pass + Kogane options
idf.py build
idf.py -p COM<x> flash monitor
```

### 3.3 `base-station/` (Python on the laptop)
```powershell
cd base-station
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e .
python -m kogane_base            # runs the orchestrator (all stubs wired together)
```

---

## 4. Recommended bring-up order

Mirrors `hardware/DESIGN.md §14`, but from the firmware side:

1. **FC alone** — flash iNAV, apply `kogane-fc.diff`, verify gyro (ICM-45686) + accel in Configurator.
2. **FC RC + motors (props off)** — bind ELRS on UART3, verify DShot order/direction, test failsafe.
3. **ESP32-S3 link** — flash companion, confirm it reads iNAV MAVLink telemetry over UART1.
4. **Base UDP loopback** — run `base-station`, confirm it exchanges `KGN` datagrams with the ESP32 over Wi-Fi.
5. **mmWave nodes** — flash ESP32-C3 nodes, confirm LD2450 targets arrive at the base as UDP.
6. **Fusion** — base produces a smooth (X, Y, heading) from mmWave (+ camera later).
7. **MSP override (motors off / tethered)** — base → ESP32 → MSP override moves the FC's virtual sticks.
8. **Payload** — camera stream, LCD, servo rollout, audio loopback.
9. **Tethered hover** with RC override ready, then enable the off-board position loop.

---

## 5. Repo layout
```
firmware/
├─ README.md                 # this file
├─ firmware.ioc              # CubeMX pinout reference (not built)
├─ shared/PROTOCOL.md        # wire formats (UDP + FC link)
├─ fc-inav/                  # iNAV target skeleton + CLI config
├─ companion-esp32s3/        # ESP-IDF companion firmware
├─ mmwave-node-esp32c3/      # ESP-IDF LD2450 bridge node
└─ base-station/             # Python base-station stack
```

## 6. Status / what is stubbed
Everything marked `TODO(kogane)` is a stub. The baseline goal is: **structure compiles,
tasks/threads exist, links are wired, and each block has one obvious place to add logic.**
