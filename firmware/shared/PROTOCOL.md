# KOGANE — Wire Protocols (shared)

Single source of truth for the message formats used across the base station, the
drone companion (ESP32-S3), and the mmWave nodes (ESP32-C3). Keep the C header
(`companion-esp32s3/main/kogane_msg.h`) and the Python module
(`base-station/kogane_base/protocol.py`) in sync with this file.

---

## 1. `KGN` UDP datagram (Wi-Fi)

All Wi-Fi UDP traffic uses one framed datagram. Little-endian. Default port **`5005`**.

```
offset  size  field        notes
0       3     magic        ASCII "KGN"
3       1     version      = 1
4       1     msg_type     see table below
5       1     flags        bit0 = ack_requested
6       2     seq          u16 rolling sequence
8       4     src_id       device id (e.g. node index, drone=0)
12      2     len          payload length
14      len   payload      msg_type-specific (below)
14+len  2     crc16        CCITT over bytes [0 .. 14+len)
```

### msg_type values
| id | name | dir | payload |
|----|------|-----|---------|
| 0x01 | `MMWAVE_TARGETS` | node → base | `mmwave_targets` |
| 0x10 | `SETPOINT` | base → drone | `setpoint` |
| 0x11 | `MODE_CMD` | base → drone | `mode_cmd` |
| 0x20 | `DRONE_STATE` | drone → base | `drone_state` |
| 0x30 | `SCREEN_FRAME` | base → drone | `screen_frame` (chunked) |
| 0x40 | `AUDIO_TTS` | base → drone | PCM/opus chunk |
| 0x41 | `AUDIO_MIC` | drone → base | PCM/opus chunk |
| 0x7F | `HEARTBEAT` | any | `heartbeat` |

### payload structs
```
mmwave_targets:   u8 count; then count × { i16 x_mm; i16 y_mm; i16 speed_cms; u16 res_mm }
setpoint:         i16 vx_cms; i16 vy_cms; i16 vz_cms; i16 yaw_rate_cds; u8 ctrl_mode
                  (ctrl_mode: 0=hold, 1=velocity, 2=position)
mode_cmd:         u8 mode  (0=idle,1=arm,2=takeoff,3=follow,4=land,5=dock,6=failsafe)
drone_state:      i16 x_cm; i16 y_cm; i16 z_cm; i16 yaw_cd; u16 batt_mv; u8 flags; u8 link_q
heartbeat:        u32 uptime_ms; u8 role   (0=base,1=drone,2=node)
```

`crc16` = CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF).

---

## 2. FC link (ESP32-S3 ↔ F722, UART1 @ 115200)

Two protocols share this UART:

- **MAVLink v2 (inbound telemetry):** iNAV is configured with a MAVLink telemetry
  port. The companion parses `HEARTBEAT`, `ATTITUDE`, `SYS_STATUS`, `GPS_RAW_INT`/
  `LOCAL_POSITION_NED` (as available) to build `DRONE_STATE`.
- **MSP v2 (outbound control):** setpoints become **MSP RC override** frames
  (`MSP_SET_RAW_RC`, or iNAV MSP override) mapping vx/vy/vz/yaw → RC channels.
  iNAV does **not** accept MAVLink setpoints, hence MSP here.

> Mapping `setpoint` → RC channels is defined in `companion-esp32s3/main/link_fc.c`.
> Keep channel order aligned with the `map`/`rc` settings in `fc-inav/config/kogane-fc.diff`.

---

## 3. Camera stream (OV2640 → laptop)

Independent of `KGN`: the companion serves **MJPEG over HTTP** (`http://<drone-ip>/stream`).
The base pulls frames for Face-ID / obstacle CV. Not on the UDP control path so it never
blocks setpoints.

---

## 4. Versioning

Bump `version` in the datagram header and this doc together. Base station rejects
mismatched versions with a logged warning.
