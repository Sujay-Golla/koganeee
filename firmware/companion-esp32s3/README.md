# KOGANE Companion — ESP32-S3-WROOM-1 (ESP-IDF)

On-board companion. Bridges the laptop (Wi-Fi UDP) to the F722 flight core, and drives
the drone payload (audio, display, camera, servo).

## Responsibilities
| Module | File | Role |
|--------|------|------|
| Wi-Fi + UDP | `main/wifi_udp.*` | join Wi-Fi (STA), send/recv `KGN` datagrams to base |
| FC link | `main/link_fc.*` | parse iNAV **MAVLink** telemetry in; send **MSP** RC override out (UART1) |
| Audio | `main/audio_i2s.*` | INMP441 mic → base; base TTS → MAX98357A speaker (I2S) |
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

## Pins (defaults; set final GPIOs in menuconfig — DESIGN.md §7)
FC UART1, I2S (mic + speaker), SPI (LCD+touch), DVP (OV2640), LEDC (servo). ESP32-S3
GPIO assignment is **not yet locked in hardware** — confirm before PCB route, then update
`Kconfig.projbuild` defaults.

## Status
All modules are FreeRTOS-task skeletons with `TODO(kogane)` stubs. `app_main` brings up
Wi-Fi, then starts each task. The control path (UDP setpoint → MSP override) and the
telemetry path (MAVLink → UDP DRONE_STATE) are wired end-to-end with placeholder logic.
