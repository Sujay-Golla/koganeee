# KOGANE Companion — ESP32-S3-WROOM-1 (ESP-IDF)

On-board companion. Bridges the laptop (Wi-Fi UDP) to the F722 flight core, and drives
the drone payload (audio, display, camera, servo).

## Responsibilities
| Module | File | Role |
|--------|------|------|
| Wi-Fi + UDP | `main/wifi_udp.*` | join Wi-Fi (STA), send/recv `KGN` datagrams to base |
| FC link | `main/link_fc.*` | parse iNAV **MAVLink** telemetry in; send **MSP** RC override out (UART1) |
| Audio | `main/audio_i2s.*` | INMP441 mic → base (`AUDIO_MIC`, off by default); base TTS → speaker amp (`AUDIO_TTS`). One I2S controller, full duplex, 16 kHz mono |
| Display | `main/display_spi.*` | ILI9341 + XPT2046 touch (SPI) |
| Camera | `main/camera_dvp.*` | OV2640 DVP → MJPEG HTTP stream |
| Servo | `main/servo_ledc.*` | MG90S screen rollout (LEDC PWM) |
| Messages | `main/kogane_msg.h` | `KGN` datagram structs (mirror of shared/PROTOCOL.md) |

## Build / flash
```powershell
idf.py set-target esp32s3
idf.py menuconfig      # Kogane -> Wi-Fi SSID/pass, base station IP/port, FC UART, pins
idf.py build
idf.py -p COM<x> flash monitor
```
Requires ESP-IDF v5.x. Camera needs the `esp32-camera` component (add via the IDF
component manager — see `main/idf_component.yml`).

## Flash layout

Custom partition table (`partitions.csv`, `CONFIG_PARTITION_TABLE_CUSTOM=y`). The
stock single-app table gave the app 1 MB and the image was already ~83% full
before the camera driver went in, on a module with 16 MB of flash.

| offset | size | name | notes |
|--------|------|------|-------|
| `0x000000` | 32 K | — | 2nd stage bootloader |
| `0x008000` | 4 K | — | partition table |
| `0x009000` | 24 K | `nvs` | **unmoved** from the stock layout |
| `0x00f000` | 4 K | `phy_init` | **unmoved** from the stock layout |
| `0x010000` | **3 M** | `factory` | app — was 1 M |
| `0x310000` | ~12.9 M | — | unallocated to the end of flash |

`nvs` and `phy_init` keep their stock offsets *and* sizes, so stored Wi-Fi and PHY
calibration survive the reflash — only the app grew, and it grew downstream of
both. One `factory` app, **no OTA slots**: there is no OTA mechanism in this
firmware and the board is flashed over native USB (the UART RXD0 castellation is
destroyed, see `PINMAP.md`), so a second slot would cost 3 MB for a path nothing
can use. **No `storage` partition**: camera frames stream straight out of PSRAM as
MJPEG and screen tiles are rendered as they land, so there is no file to keep.
Full rationale is in the comment block in `partitions.csv`.

## Camera HTTP endpoints

`camera_dvp.c` serves, on `CONFIG_KGN_CAM_HTTP_PORT` (80):

| path | content | purpose |
|------|---------|---------|
| `/stream` | `multipart/x-mixed-replace` MJPEG | the CV feed, `PROTOCOL.md` §3 |
| `/snapshot` | one `image/jpeg` | cheapest "is the camera alive" check |
| `/` | HTML status | frame size, quality, fps cap, IP, counters |

> **This server is unauthenticated.** No password, no token, no TLS, and `/stream`
> is a live camera feed. Anyone who can route to the drone's address can watch it.
> Fine on an isolated bench network, not fine on a shared one.

## Pins (defaults; set final GPIOs in menuconfig — DESIGN.md §7)
FC UART1, I2S (mic + speaker), SPI (LCD+touch), DVP (OV2640), LEDC (servo). ESP32-S3
GPIO assignment is **not yet locked in hardware** — confirm before PCB route, then update
`Kconfig.projbuild` defaults.

## Status
All modules are FreeRTOS-task skeletons with `TODO(kogane)` stubs. `app_main` brings up
Wi-Fi, then starts each task. The control path (UDP setpoint → MSP override) and the
telemetry path (MAVLink → UDP DRONE_STATE) are wired end-to-end with placeholder logic.
