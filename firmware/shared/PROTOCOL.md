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
| 0x40 | `AUDIO_TTS` | base → drone | `audio_chunk` (chunked) |
| 0x41 | `AUDIO_MIC` | drone → base | `audio_chunk` (chunked) |
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

### `drone_state.flags` — per-field validity bitmask

`drone_state` is a fixed 12 bytes, but the drone does not always know every
field. `flags` says which ones are real. **A field whose bit is clear carries no
data and its bytes are zero — that is not a measurement of zero.**

| bit | name | meaning when set |
|-----|------|------------------|
| 0 | `POS_VALID` | `x_cm`, `y_cm`, `z_cm` are real |
| 1 | `YAW_VALID` | `yaw_cd` is real |
| 2 | `BATT_VALID` | `batt_mv` is real |
| 3 | `LINKQ_VALID` | `link_q` is real |
| 4 | `FC_LINK_UP` | companion received an FC heartbeat within 3 seconds; does not imply control transmission |
| 5 | `ARMED` | FC reports armed (implies `FC_LINK_UP`) |
| 6-7 | — | reserved, must be 0 |

`link_q` is 0..100, mapped from Wi-Fi RSSI over the range -95 dBm -> 1 and
-35 dBm -> 100 (the value 0 is reserved for "unknown").

> **Current receive-only bridge:** CRC-checked MAVLink HEARTBEAT sets FC link
> and armed status for up to 3 seconds. ATTITUDE yaw expires after 1 second;
> SYS_STATUS voltage expires after 3 seconds (0 or 65535 means unavailable).
> FC fields are invalid when the heartbeat expires. Position remains invalid.
> LINKQ_VALID comes from Wi-Fi association/RSSI, and heartbeat uptime is real.
> Roll/pitch are available in the ESP32 log but are not in this 12-byte payload.

### `mode_cmd` (0x11) — what the drone actually does with it

The companion records the mode and drives the retractable screen mechanism from
it. Flight behaviour (arming, takeoff, landing, docking) is **not** implemented
and remains disabled while the FC link is tested in receive-only mode.

| mode | screen mechanism | flight action |
|------|------------------|---------------|
| 0 `idle` | retract | none |
| 1 `arm` | retract | not implemented |
| 2 `takeoff` | retract | not implemented |
| 3 `follow` | **deploy** | not implemented |
| 4 `land` | retract | not implemented |
| 5 `dock` | **deploy** | not implemented |
| 6 `failsafe` | retract | not implemented |

Servo moves are rate limited on the drone (default 400 ms minimum between
accepted commands), so flooding 0x11 will not thrash the mechanism — excess
commands are dropped and counted.

### `screen_frame` (0x30) — chunked panel updates

The drone panel is an **ILI9341 320x240** landscape LCD. Every 0x30 payload
begins with the same 8-byte sub-header, then a format-specific body. Chunks are
independent: there is no reassembly buffer on the drone, each chunk is rendered
as it arrives, so loss degrades to a missing tile rather than a dropped frame.

```
screen_frame sub-header (8 bytes, at payload offset 0):
offset  size  field       notes
0       1     fmt         1 = RGB565 tile, 2 = TEXT line
1       1     frame_id    rolling u8, groups the chunks of one logical frame
2       1     chunk_idx   0-based index within the frame
3       1     chunk_cnt   total chunks in the frame, or 0 when streaming
4       1     flags       bit0 = FIRST   clear the panel before applying
                          bit1 = LAST    last chunk of this frame
                          bit2 = STATUS  release the panel back to the drone's
                                         own status screen; body is ignored
5       3     reserved    must be 0
```

**`fmt = 1` (RGB565 tile)** — body is a tile header then raw pixels:

```
offset  size    field    notes
8       2       x        u16 left edge, pixels, 0..319
10      2       y        u16 top edge, pixels, 0..239
12      2       w        u16 width,  x + w <= 320
14      2       h        u16 height, y + h <= 240
16      w*h*2   pixels   RGB565 **little-endian**, row-major, no padding
```

Budget: a 1500-byte MTU leaves 1500 - 28 (IP/UDP) - 14 (KGN header) - 2 (crc)
- 8 (sub-header) - 8 (tile header) = **1440 bytes = 720 pixels** per datagram.
A full-width strip of `w=320, h=2` is 1280 bytes and fits comfortably; a full
320x240 frame is therefore 120 such chunks. The drone rejects any tile larger
than its band buffer (320 x 32 = 10240 px), so `h <= 32` for full-width tiles.

**`fmt = 2` (TEXT line)** — body is a line header then ASCII:

```
offset  size  field    notes
8       1     row      text row index, 0..9 (each row is 24 px tall)
9       1     scale    glyph scale 1..3 over a 6x8 cell (clamped on the drone)
10      2     fg       u16 RGB565 foreground
12      2     bg       u16 RGB565 background (the row is cleared to this)
14      n     text     ASCII 0x20..0x7E, **not** NUL-terminated, n = len - 14
```

`n` is capped at 53 characters (320 px / 6 px cell at scale 1); anything longer
is truncated, not wrapped. Characters outside 0x20..0x7E render as `?`. The
drone uses a built-in 5x7 font, so no glyph negotiation is needed.

Behaviour notes the Python renderer must match:

- Sending any non-`STATUS` chunk takes the panel away from the drone's local
  status screen. The drone hands it back automatically after **5 s** with no
  further chunks, or immediately on a chunk with the `STATUS` flag set.
- `frame_id`, `chunk_idx` and `chunk_cnt` are informational today — the drone
  renders every chunk immediately and does not wait for a complete frame. They
  are in the header so a future implementation can buffer without a version bump.
- Malformed chunks (bad geometry, short body, unknown `fmt`) are counted and
  dropped, with a rate-limited warning. They never abort the stream.

### `audio_chunk` (0x40 `AUDIO_TTS`, 0x41 `AUDIO_MIC`) — streamed audio

Both directions use **one identical layout**. The two are the same codec, the
same rate and the same framing, so there is one thing to get right rather than
two. This section replaces the earlier "PCM/opus chunk" entry, which was not a
specification: a receiver could not tell what it was being handed.

**Opus is not implemented and is not planned for v1.** The codec is raw PCM.

```
audio_chunk sub-header (4 bytes, at payload offset 0):
offset  size  field    notes
0       1     fmt      1 = PCM_S16LE, 2 = CTRL
1       1     flags    bit0 = START  first chunk of this utterance/stream;
                               the receiver flushes any backlog first
                       bit1 = END    last chunk of this utterance/stream
                       bits2-7 reserved, must be 0
2       2     seq      u16 rolling chunk index *within this audio stream*
                       (not the datagram header seq, which spans all msg types)
```

The sub-header is 4 bytes so the PCM body starts 2-byte aligned inside the
payload and both ends can treat it as an `int16_t` array in place.

**`fmt = 1` (PCM_S16LE)** — body is raw PCM, and the format is fixed, not
negotiated. A receiver seeing `fmt = 1` may assume all of this without looking
any further:

| property | value |
|----------|-------|
| sample rate | **16000 Hz** |
| sample format | **signed 16-bit, little-endian** |
| channels | **1 (mono)** |
| body length | `len - 4` bytes = `(len - 4) / 2` samples, always even |

```
offset  size    field     notes
4       len-4   samples   int16 LE mono PCM @ 16 kHz
```

Chunk size budget: 1500 MTU - 28 (IP/UDP) - 14 (KGN header) - 2 (crc) - 4
(sub-header) = 1452 usable, capped at **1440 bytes = 720 samples = 45 ms**.
The drone sends mic audio in **512-sample (32 ms, 1024-byte)** chunks, which is
a 1044-byte datagram. Anything longer than 1440 bytes of body is dropped.

Why 16 kHz mono and not something better: the drone's mic and speaker share one
I2S bus in full duplex, so the hardware cannot clock the two directions at
different rates — one rate has to serve both. 16 kHz is the speech-band choice,
and it costs 256 kbit/s in each direction on a link that also carries setpoints.
The rate is a single Kconfig value on the drone (`CONFIG_KGN_AUDIO_SAMPLE_RATE`);
if it is moved off 16000 then `fmt = 1` no longer describes the wire and the
firmware says so loudly at boot. Do not move it without changing this table.

**`fmt = 2` (CTRL)** — base → drone only, one command byte, no audio:

```
offset  size  field  notes
4       1     cmd    1 = MIC_ON, 2 = MIC_OFF, 3 = SELFTEST, 4 = FLUSH
```

| cmd | effect on the drone |
|-----|---------------------|
| 1 `MIC_ON` | start streaming `AUDIO_MIC` to the base |
| 2 `MIC_OFF` | stop streaming `AUDIO_MIC` — **this is the boot default** |
| 3 `SELFTEST` | play the local speaker self-test tone sequence |
| 4 `FLUSH` | drop all queued TTS audio and go silent immediately |

CTRL rides inside 0x40 rather than taking a new `msg_type` so that turning the
microphone on and off needs no protocol version bump. It is base → drone by
definition; a CTRL chunk arriving on 0x41 is meaningless and is ignored.

Behaviour notes the Python side must match:

- **`AUDIO_MIC` is off until the base asks for it.** The drone boots with
  streaming disabled and only starts on `fmt 2 cmd 1`. This is a privacy
  position, not an optimisation: it is a microphone on an aircraft that follows
  people, and it must not be possible to leave it on by accident.
- The drone's TTS playback queue holds 12 chunks. When it overflows the **oldest**
  queued chunk is dropped, never the newest and never the UDP receive path. If
  the base streams faster than real time it will lose the *beginning* of the
  backlog, not the audio it just sent.
- `seq` is informational: neither side reorders, retransmits or conceals loss. A
  gap in `seq` is an audible gap.
- A short body, an odd body length, an unknown `fmt` or a body over 1440 bytes is
  counted and dropped with a rate-limited warning. Chunks are never reassembled.
- Sending 0x40 does not require the mic to be working, and vice versa — but note
  the drone's two directions share a clock, so on the drone side they fail
  together when that clock is wrong. See `companion-esp32s3/PINMAP.md`.
- **The drone's speaker path is gated OFF by default in firmware and must be
  enabled explicitly.** `CONFIG_KGN_AUDIO_TX_ENABLE` defaults to `n`, so a stock
  build allocates no I2S TX channel: `AUDIO_TTS` `fmt 1` chunks are still
  accepted, counted and then discarded rather than played, and `fmt 2 cmd 3`
  (`SELFTEST`) is answered with a log line saying the path is disabled instead of
  a tone. Nothing on the wire changes and nothing errors — the base station
  cannot tell from the protocol whether audio is audible, because there is no
  reverse channel for it. The gate exists because a clocked class-D amplifier
  with a data line that might not be connected is a thermal hazard, not a silent
  failure; see `companion-esp32s3/PINMAP.md`. Enabling it needs a menuconfig
  change and a reflash on the drone.

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
