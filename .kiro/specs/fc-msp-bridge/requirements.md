# Requirements Document

## Introduction

The ESP32-S3 companion on the KOGANE flight controller is the only path between the base station and the STM32F722 running iNAV 9.1. This spec covers that bridge: inbound iNAV MAVLink v2 telemetry parsed into `KGN DRONE_STATE` datagrams and forwarded to the base station over UDP, and outbound `KGN SETPOINT` datagrams converted into iNAV MSP v2 `MSP_SET_RAW_RC` frames. See `firmware/shared/PROTOCOL.md` §2 and `firmware/companion-esp32s3/main/link_fc.c`.

Fixed constraints this spec is built on:

- The only ESP32↔STM32 serial link on this PCB is GPIO43 (TXD0, net `ESP32-TX` → STM32 PA9) and GPIO44 (RXD0, net `ESP32-RX` → STM32 PA10). The IDF console defaults to the same two pads. `CONFIG_KGN_PINS_OWNER_CONSOLE` vs `CONFIG_KGN_PINS_OWNER_FC_LINK` selects the owner; `link_fc_start()` is currently inert because the console owns them. Selecting the FC link requires `CONFIG_ESP_CONSOLE_NONE=y`, which kills all console output including the boot log. Native USB (IO19/20) is unconnected in the netlist, so USB-serial-JTAG is not a fallback. Once the FC link is live, UDP telemetry is the only diagnostic channel.
- iNAV 9.1 in `~/inav` already compiles the needed support: `src/main/target/common.h:158` `#define USE_RX_MSP`, `:159` `#define USE_MSP_RC_OVERRIDE`. No custom rebuild is required for MSP RC.
- `src/main/rx/msp.c:79` sets `rxRuntimeConfig->rxSignalTimeout = DELAY_5_HZ`; `src/main/rx/rx.h:50` defines `DELAY_5_HZ` as `1000000 / 5` µs = **200 ms**. `MSP_SET_RAW_RC` must arrive faster than 5 Hz or iNAV declares RC signal loss. `rx.h:96` defines `MAX_INVALID_RX_PULSE_TIME` as 300 ms.
- `rx.h:65` has `RX_TYPE_MSP`, so `set receiver_type = MSP` is valid. The alternative is the `BOXMSPRCOVERRIDE` flight mode with the `mspOverrideChannels` bitmask (`rx.h:129`), which overlays MSP values onto a real receiver's channels. There is no RC transmitter on this aircraft, so full `receiver_type = MSP` is the applicable path and the overlay mode is a non-goal.
- The FC config sets `failsafe_procedure = DROP`. With MSP as the receiver, a stalled ESP32 task, a Wi-Fi stall, or a >200 ms scheduling hiccup is an in-air motor cut.
- MSP v2 framing in `link_fc.c`: `$X<`, flags byte, u16 function LE, u16 size LE, payload, CRC8 DVB-S2 (poly 0xD5) over header bytes [3..7] plus payload. `MSP_SET_RAW_RC` is function 200, payload 8 × u16 channel values in µs, nominally 1000–2000. The existing `link_fc_apply_setpoint()` mapping is a marked linear placeholder; `parse_mavlink()` is an empty stub.
- `KGN SETPOINT` payload: i16 `vx_cms`, i16 `vy_cms`, i16 `vz_cms`, i16 `yaw_rate_cds`, u8 `ctrl_mode` (0=hold, 1=velocity, 2=position). `KGN DRONE_STATE` payload: i16 `x_cm`, i16 `y_cm`, i16 `z_cm`, i16 `yaw_cd`, u16 `batt_mv`, u8 `flags`, u8 `link_q`.

## Glossary

- **FC** — The flight controller: the STM32F722 on the KOGANE board running iNAV 9.1.
- **companion** — The ESP32-S3 on the same board, the only path between the base station and the FC. Hosts the bridge described here.
- **base station** — The ground-side system that sends `SETPOINT` datagrams over UDP and consumes `DRONE_STATE`.
- **MSP** — MultiWii Serial Protocol, the request/response serial protocol iNAV exposes on a UART. Used here to push RC values into the FC.
- **MSP v2** — The version 2 MSP framing used by this bridge: `$X<`, flags byte, u16 function LE, u16 size LE, payload, CRC8 DVB-S2 (poly 0xD5) over header bytes [3..7] plus payload.
- **`MSP_SET_RAW_RC`** — MSP function 200, payload of 8 × u16 channel values in microseconds (nominally 1000–2000). The message that delivers RC channel values to the FC.
- **MAVLink v2** — The telemetry protocol iNAV streams on the same UART, parsed inbound for attitude, battery, and position data.
- **KGN datagram** — A framed message on the UDP link between companion and base station, per `PROTOCOL.md` §1: magic, version, length, rolling `seq`, payload, CRC16/CCITT-FALSE.
- **SETPOINT** — The inbound KGN datagram carrying a commanded motion: `vx_cms`, `vy_cms`, `vz_cms`, `yaw_rate_cds`, and `ctrl_mode`.
- **DRONE_STATE** — The outbound KGN datagram carrying telemetry and status: position, `yaw_cd`, `batt_mv`, `flags`, and `link_q`.
- **link-loss state** — The bridge state entered when no valid setpoint is current, Wi-Fi is down, the UDP send path fails, or the MSP transmit task is detected as failed. Its RC behaviour is a single documented configuration.
- **maximum setpoint age** — The configured age limit, no more than 250 ms, beyond which the most recently accepted setpoint stops counting as a valid command.
- **`rxSignalTimeout`** — iNAV's RC signal loss timeout. For the MSP receiver it is `DELAY_5_HZ`, 200 ms; MSP RC frames must arrive faster than that.
- **receiver_type MSP** — The iNAV setting (`RX_TYPE_MSP`) that makes MSP the sole RC source, with no physical receiver. The applicable path for this aircraft.
- **BOXMSPRCOVERRIDE** — The iNAV flight mode that overlays MSP channel values onto a real receiver's channels via `mspOverrideChannels`. A non-goal here, since there is no RC transmitter.
- **failsafe_procedure DROP** — The FC's configured failsafe action: on RC signal loss, motors stop. Makes any stall in the MSP transmit path an in-air motor cut.
- **aux channel** — An RC channel used for switch functions rather than attitude, including the channel iNAV configures as the arming switch.
- **neutral value** — The defined per-channel RC value representing no command, used at boot, in hold mode, and potentially in link-loss state.

## Requirements

### Requirement 1: UART pin ownership and the console tradeoff

**User Story:** As a firmware developer, I want pin ownership between the IDF console and the FC link to be explicit and enforced at build time, so that I never have stdout and MSP traffic fighting on the same two pads and I always know which diagnostics I still have.

#### Acceptance Criteria

1. WHEN the firmware is built with `CONFIG_KGN_PINS_OWNER_CONSOLE=y` THEN the system SHALL NOT install a UART driver on GPIO43/44 for the FC link, SHALL leave `link_fc_apply_setpoint()` as a no-op, and SHALL log one warning at startup naming the configured TX and RX pins.
2. WHEN the firmware is built with `CONFIG_KGN_PINS_OWNER_FC_LINK=y` AND `CONFIG_ESP_CONSOLE_NONE` is not set THEN the build SHALL fail or emit a compile-time diagnostic that names `CONFIG_ESP_CONSOLE_NONE=y` as the required setting.
3. WHEN the firmware is built with `CONFIG_KGN_PINS_OWNER_FC_LINK=y` AND `CONFIG_ESP_CONSOLE_NONE=y` THEN the system SHALL route the FC UART to TX=GPIO43 / RX=GPIO44 at 115200 8N1, no flow control.
4. IF the FC link owns the pins THEN the system SHALL treat UDP as the sole diagnostic channel and SHALL emit a `DRONE_STATE` datagram carrying at least link quality and battery voltage at a fixed minimum rate even when no MAVLink telemetry has been received.
5. IF the FC link owns the pins THEN the system SHALL NOT route any log, printf, or panic output to GPIO43/44 at any point, including boot, brownout, and abort paths.
6. WHEN the FC link owns the pins THEN the system SHALL expose the state that would otherwise be logged (boot completion, Wi-Fi association, MSP TX cadence, parse error counters) as fields or flags inside `DRONE_STATE` or a diagnostic datagram.
7. WHILE the console owns the pins the system SHALL treat every `link_fc` code path as untested with respect to real FC traffic, and documentation SHALL state that `link_fc` logs in that configuration prove nothing about the FC link.

### Requirement 2: Outbound MSP transmission

**User Story:** As a pilot on the bench, I want MSP RC frames to be byte-correct and to arrive comfortably faster than iNAV's 5 Hz floor, so that iNAV never declares RC signal loss while the bridge is healthy.

#### Acceptance Criteria

1. WHEN the system encodes an MSP v2 frame THEN it SHALL emit `$`, `X`, `<`, a flags byte of 0, the function as u16 little-endian, the payload size as u16 little-endian, the payload, and a CRC8 DVB-S2 (poly 0xD5) computed over header bytes [3..7] followed by every payload byte.
2. WHEN the system sends an RC update THEN it SHALL use function 200 (`MSP_SET_RAW_RC`) with a payload of exactly 8 × u16 channel values in microseconds, each within 1000–2000 inclusive.
3. WHILE the bridge is asserting control the system SHALL transmit `MSP_SET_RAW_RC` at a nominal rate of at least 20 Hz, giving at least 4× margin over iNAV's 200 ms `rxSignalTimeout`.
4. WHILE the bridge is asserting control the system SHALL NOT allow the interval between two consecutive `MSP_SET_RAW_RC` frames to exceed 100 ms.
5. IF the measured inter-frame interval exceeds 100 ms THEN the system SHALL record the overrun in a counter reported in telemetry.
6. IF the measured inter-frame interval exceeds 150 ms THEN the system SHALL treat the TX path as failed and enter the link-loss behaviour of Requirement 4 rather than continuing to send stale frames.
7. WHEN a frame is written to the UART THEN the write SHALL be bounded by a timeout such that a full or blocked TX FIFO cannot stall the transmit task past the 100 ms budget.
8. WHEN the TX task cannot meet its deadline because the UART write timed out THEN the system SHALL increment a distinct counter for UART-blocked versus scheduling-caused overruns.

### Requirement 3: Setpoint validation and staleness

**User Story:** As a developer, I want every setpoint bounds-checked and aged out before it reaches the RC mapping, so that a corrupt, extreme, or old datagram cannot produce a full-deflection stick input.

#### Acceptance Criteria

1. WHEN a `SETPOINT` payload is received THEN the system SHALL reject it unless the payload length is exactly 9 bytes and the datagram CRC16 validates.
2. WHEN a `SETPOINT` payload is accepted THEN the system SHALL clamp `vx_cms`, `vy_cms`, and `vz_cms` to a configured per-axis limit and `yaw_rate_cds` to a configured yaw-rate limit before any RC mapping.
3. IF any field required clamping THEN the system SHALL increment a clamp counter reported in telemetry.
4. WHEN `ctrl_mode` is 0 (hold) THEN the system SHALL map all attitude axes to their neutral RC value and SHALL ignore the velocity fields in the same payload.
5. WHEN `ctrl_mode` is 1 (velocity) THEN the system SHALL map the clamped velocity and yaw-rate fields onto RC channels using the configured mapping.
6. WHEN `ctrl_mode` is 2 (position) THEN the system SHALL either implement the documented position behaviour or reject the payload and report an unsupported-mode counter; it SHALL NOT silently fall through to velocity mapping.
7. IF `ctrl_mode` holds any value other than 0, 1, or 2 THEN the system SHALL discard the payload and increment an invalid-mode counter.
8. WHEN the most recently accepted setpoint is older than a configured maximum setpoint age of no more than 250 ms THEN the system SHALL stop treating it as a valid command and SHALL apply the link-loss behaviour of Requirement 4.
9. WHILE no setpoint has ever been received since boot the system SHALL NOT transmit `MSP_SET_RAW_RC` frames derived from default or zero-initialised setpoint state.
10. WHEN a setpoint arrives with a `seq` value that is not newer than the last accepted `seq`, accounting for u16 rollover THEN the system SHALL discard it as a duplicate or replay.

### Requirement 4: Failsafe and link loss

**User Story:** As the person standing next to a powered aircraft, I want the bridge's behaviour on UDP silence, Wi-Fi loss, and task failure to be one deliberate documented decision, so that I know whether a dropped link means a controlled stop or a motor cut.

#### Acceptance Criteria

1. WHEN no valid `SETPOINT` has been received for longer than the maximum setpoint age THEN the system SHALL enter link-loss state and SHALL NOT continue repeating the last received setpoint.
2. WHILE in link-loss state the system SHALL either transmit the defined neutral/safe RC frame set at the Requirement 2 cadence, or deliberately cease MSP transmission so that iNAV's own failsafe triggers; the chosen behaviour SHALL be a single documented configuration and SHALL NOT vary by code path.
3. IF the chosen link-loss behaviour is to cease transmission THEN the documentation SHALL state that with `failsafe_procedure = DROP` this results in motors stopping, and the system SHALL NOT be run with props on until that is intended.
4. WHEN Wi-Fi disconnects THEN the system SHALL enter link-loss state within one maximum-setpoint-age interval, without waiting for a socket-level timeout.
5. WHEN the UDP socket is invalid or `wifi_udp_send()` fails THEN the system SHALL treat the base-station link as down for the purposes of link-loss state.
6. WHEN Wi-Fi reassociates and a fresh valid setpoint arrives THEN the system SHALL NOT resume asserting control automatically unless the base station has re-established an explicit armed/controlling state.
7. IF the MSP transmit task stops running, is starved, or overflows its stack THEN a watchdog SHALL detect it within 150 ms and SHALL drive the system into link-loss state.
8. WHEN the FreeRTOS task watchdog fires on the FC link task THEN the system SHALL reboot rather than continue in an unknown control state.
9. WHILE the system is in link-loss state it SHALL report that state in `DRONE_STATE` flags so the base station can distinguish "bridge healthy, no command" from "bridge gone".
10. WHEN the system transitions into or out of link-loss state THEN it SHALL record the transition with a timestamp retrievable over UDP, since no console log exists.

### Requirement 5: Inbound MAVLink v2 telemetry

**User Story:** As a base-station developer, I want iNAV's MAVLink stream turned into `DRONE_STATE` datagrams that are honest about what is missing, so that the UI never shows stale or invented numbers.

#### Acceptance Criteria

1. WHEN bytes arrive on the FC UART THEN the system SHALL feed them through a MAVLink v2 parser that tolerates arbitrary chunk boundaries, including a single byte at a time and frames split across reads.
2. WHEN an `ATTITUDE` message is parsed THEN the system SHALL update `yaw_cd` in the pending `DRONE_STATE`.
3. WHEN a `SYS_STATUS` or equivalent battery message is parsed THEN the system SHALL update `batt_mv`.
4. WHEN a `LOCAL_POSITION_NED` or `GPS_RAW_INT` message is parsed THEN the system SHALL update `x_cm`, `y_cm`, and `z_cm`.
5. IF a field's source message has not been received since boot THEN the system SHALL mark that field invalid in `DRONE_STATE` flags rather than sending zero as if it were a measurement.
6. IF a field's source message has not been received within a configured freshness window THEN the system SHALL mark that field stale in `DRONE_STATE` flags.
7. WHEN a frame fails its MAVLink CRC, carries an unknown message ID, or has an unexpected length THEN the system SHALL discard only that frame, SHALL increment a parse-error counter, and SHALL resynchronise on the next start byte without dropping subsequent valid frames.
8. WHEN a stream of pure garbage bytes is received THEN the parser SHALL not block, allocate unboundedly, or overrun its buffer.
9. WHILE MAVLink telemetry is absent the system SHALL still emit `DRONE_STATE` at its heartbeat rate with all measurement fields marked invalid and `link_q` reflecting the dead FC link.
10. WHEN `DRONE_STATE` is emitted THEN it SHALL be framed per `PROTOCOL.md` §1 with correct magic, version, length, rolling `seq`, and CRC16/CCITT-FALSE.

### Requirement 6: Arming and mode safety

**User Story:** As the operator, I want it to be structurally impossible for a malformed or replayed datagram to arm the aircraft, so that a network glitch cannot spin props.

#### Acceptance Criteria

1. WHEN the system maps a setpoint to RC channels THEN it SHALL NOT write any value to an aux channel that iNAV has configured as an arming switch.
2. WHEN the system is not in an explicitly armed state THEN it SHALL hold every aux channel at its configured disarmed value regardless of datagram contents.
3. WHEN a `SETPOINT` datagram is received THEN it SHALL NOT be able to change arm state by any code path; arming SHALL require a distinct, separately validated message.
4. IF an arming request is received THEN the system SHALL require the datagram to pass CRC validation and the replay check of Requirement 3 before acting on it.
5. WHEN throttle is derived from `vz_cms` THEN the resulting channel value SHALL NOT exceed a configured bench-safe ceiling unless a build-time or runtime flight-enable flag is set.
6. WHEN the system boots THEN all 8 channels SHALL start at their defined neutral/disarmed values and SHALL remain there until a valid setpoint and an explicit control-enable are both present.
7. IF the system enters link-loss state THEN it SHALL clear any armed state it is tracking so that recovery cannot silently resume armed control.

### Requirement 7: FC-side configuration preconditions

**User Story:** As a developer, I want the FC's own configuration verified before I trust the bridge, so that I am not debugging ESP32 code when the receiver type was never switched.

#### Acceptance Criteria

1. WHEN the bridge is commissioned THEN the FC SHALL be verified to report `receiver_type = MSP` and `feature RX_MSP` enabled.
2. WHEN the bridge is commissioned THEN the FC SHALL be verified to have MSP enabled on the UART wired to PA9/PA10 at 115200, matching the ESP32 baud.
3. WHEN the bridge is commissioned THEN the FC SHALL be verified to have MAVLink telemetry enabled on that same UART at a rate the ESP32 parser can absorb without starving the MSP transmit path.
4. WHEN the bridge is commissioned THEN `failsafe_procedure` SHALL be read back and recorded, and the documented link-loss behaviour SHALL match the value found.
5. IF any of the above verifications fails THEN the bridge SHALL be treated as untrusted and SHALL NOT be run with props installed.
6. WHEN the FC configuration is verified THEN the exact CLI commands used and their output SHALL be recorded in the handoff so the check is repeatable after any FC reflash.
7. IF the FC is reflashed or its config is reset THEN every precondition in this requirement SHALL be re-verified before the bridge is used again.

### Requirement 8: Bench-test observability

**User Story:** As a developer with no radio and props off, I want to confirm the bridge works end to end from the base station alone, so that I can validate behaviour before anything can fly.

#### Acceptance Criteria

1. WHEN a bench test runs with props removed THEN the developer SHALL be able to confirm from base-station output alone that `DRONE_STATE` is arriving, at what rate, and which fields are valid.
2. WHEN a setpoint is sent from the base station THEN the developer SHALL be able to observe the resulting RC channel values, either echoed in a diagnostic datagram or read from the FC's own channel display.
3. WHEN the developer deliberately stops sending setpoints THEN the observable behaviour SHALL match the documented link-loss decision within the maximum setpoint age.
4. WHEN the bridge is running THEN counters for MSP TX overruns, UART-blocked writes, setpoint clamps, replay rejections, invalid modes, and MAVLink parse errors SHALL all be readable over UDP.
5. WHILE the console owns GPIO43/44 the developer SHALL be able to exercise the setpoint and telemetry paths against a loopback or a second UART fixture, so the bridge logic is testable without giving up the console.
6. WHEN a bench test session completes THEN the observed MSP frame rate and its worst-case inter-frame gap SHALL be recorded, since those numbers are what the 200 ms iNAV timeout is judged against.

## Non-Goals

- MSP RC override overlay mode (`BOXMSPRCOVERRIDE` + `mspOverrideChannels`). There is no RC transmitter to overlay onto.
- ELRS receiver integration.
- Autonomous flight behaviour: takeoff, land, dock, follow, position hold logic.
- Camera, audio, and display payloads (`SCREEN_FRAME`, `AUDIO_TTS`, `AUDIO_MIC`) and the MJPEG stream.
- Partition table and flash layout changes.

## Open Questions

1. **RC channel order.** The placeholder mapping assumes AETR (roll, pitch, throttle, yaw). This depends on the iNAV `map` setting, which has not been read back. What is `map` set to on this FC, and which of the 8 channels are aux?
2. **Neutral/safe RC values at startup.** What should each of the 8 channels hold before the first setpoint arrives and while in link-loss state, for an MSP receiver with no calibrated transmitter?
3. **Throttle mapping.** Should `vz_cms` map to a hold value around mid-stick, to a floor near minimum, or to a separately commanded absolute throttle? This changes what "neutral" means for channel 3.
4. **Target setpoint rate.** Requirement 2 proposes 20 Hz MSP TX with a 100 ms hard ceiling. What rate does the base station actually intend to send `SETPOINT` at, and should the bridge interpolate or repeat between arrivals up to the staleness limit?
5. **Link-loss decision.** Neutral frames at full cadence, or cease transmission and let iNAV's `DROP` failsafe fire? This is a safety choice, not an implementation detail.
