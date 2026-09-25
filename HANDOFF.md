# Handoff — Kogane (2026-09-23)

Self-contained. Assume no memory of prior sessions. Workspace: `C:\Users\sujay\OneDrive\Documents\koganeee`. Windows. Radio (ELRS TX) arrives tomorrow.

**Read this first:** a very large amount of firmware was written this session and almost none of it has executed on the board. Every section below is tagged:

- **[HW-VERIFIED]** — observed on the physical board.
- **[BUILDS-ONLY]** — compiles and links, never run on hardware.
- **[NETLIST]** — derived from the PCB netlist/BOM, not bench-measured.

---

## Goal

Two independent tracks. Keep them independent.

1. **Flight** — iNAV on the STM32F722, flown on RC only (CRSF into UART3). Working, see the iNAV section.
2. **Companion** — ESP32-S3-WROOM-1-N16R8 (U4) doing Wi-Fi link, camera, LCD, servo, audio. Firmware written, mostly unexercised.

Current state: companion boots, Wi-Fi associates, UDP inbound validated. Peripherals untested. One unresolved hardware overheat.

---

## Status summary

| Area | State |
|---|---|
| ESP32 flash + boot | [HW-VERIFIED] |
| Console / flash path | [HW-VERIFIED] native USB bodge, COM11 |
| Wi-Fi association | [HW-VERIFIED] `10.28.43.18` |
| UDP inbound validation | [HW-VERIFIED] CRC + length rejects counted |
| Telemetry out, servo, LCD, audio, camera | [BUILDS-ONLY] |
| Base station (Python) | 593 tests pass against loopback; never against the drone |
| Pin map | [NETLIST] `firmware/companion-esp32s3/PINMAP.md` is authoritative |
| Board overheating near SW3 | **OPEN, unresolved** |
| iNAV / flight | [HW-VERIFIED] except failsafe and hover |

---

## 1. Console and flash path — [HW-VERIFIED]

The UART **RXD0 castellation on the WROOM module is physically destroyed**. UART0 flashing is dead.

A USB breakout was hand-soldered directly to module pads **13/14 (IO19/IO20 = D-/D+)**, which the PCB never routed. The board now enumerates as **VID_303A / PID_1001 on COM11** with `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`. This is both the flash path and the log path.

**Those two bodge wires are the first thing to check on a "dead board".**

Superseded: the old FT232-on-UART0 procedure and the "hold SW1 for UART pin contention" dance. Ignore them; RXD0 no longer exists.

Still-valid hardware mod: **ESP32-EN** (WROOM pad 3) is on a net shared only with STM32 PB4 and had no pull-up anywhere — it floated at 0 V. A **10 kΩ** was tacked from pad 2 (3V3) to pad 3 (EN); EN now reads 3.3 V. Do not hard-wire EN to 3.3 V. Next PCB rev: EN gets its own 10 k + 1 µF and PB4 should not own the net.

## 2. The app only runs if SW3 is held at reset — [HW-VERIFIED]

**R22 is a 10 k pulldown on IO0.** Net `/ESP32/IO0` has three connections: U4 pad IO0, R22 (pad 2 → GND, 10 k), SW3 (pad 1 → +3.3 V). The S3 internal pull-up is ~45 k, so IO0 idles near 0.6 V and **every reset lands in download mode**.

Semantics are inverted from the usual convention:

| SW3 | IO0 | Result |
|---|---|---|
| held | 3.3 V | **app boots** |
| released | ~0.6 V | download mode |

**Tape SW3 down.**

**The trap that cost a whole false diagnosis:** esptool ends every operation with `Hard resetting via RTS pin`. With IO0 low that reset lands straight back in the bootloader. So you can flash successfully, walk away, and the app never starts — while the log stays silent and looks like a firmware hang.

Pending rework: lift R22's **GND-side** pad and wire it to 3V3, converting it to a pull-up so IO0 idles high. After that SW3 becomes a no-op and forcing download mode means shorting IO0 to GND by hand. Next PCB rev: R22 = 10 k to 3V3, SW3 shorts IO0 to GND.

## 3. Confirming what is actually on the board without flashing — [HW-VERIFIED]

```
esptool --chip esp32s3 -p COM11 --before no-reset read-flash 0x10000 0x100 hdr.bin
```

Parse `esp_app_desc_t` at offset 0x20: magic `0xABCD5432`, version 0x30, project_name 0x50, time 0x70, date 0x80. This is how it was established that the current build *was* flashed and the app simply was not running (see SW3 above).

## 4. Wi-Fi — [HW-VERIFIED]

| Item | Value |
|---|---|
| SSID | `Sujay's Pixel` (phone hotspot) |
| Security | WPA2-PSK |
| Channel | 11 (2.4 GHz) |
| RSSI | -32 dBm |
| Drone | `10.28.43.18` |
| Laptop | `10.28.43.250` |
| Gateway (phone) | `10.28.43.165` |

Set via `KGN_WIFI_SSID` / `KGN_WIFI_PASS` / `KGN_BASE_IP`.

**Trap:** the SSID was first entered in menuconfig *with quote characters typed in*, which stored `"\"Sujay's Pixel\""` and would never associate. menuconfig string fields take **bare text**.

Hotspot leases change — the drone IP may move. Re-check before blaming firmware.

`esp_wifi_set_ps(WIFI_PS_NONE)` is now called. Real packet loss was measured with power save on (`wifi:pm start, type: 1`). A power-save stall is indistinguishable from RC loss, and iNAV's failsafe is DROP.

## 5. UDP inbound verified end to end — [HW-VERIFIED]

Deliberately corrupted KGN datagrams were sent from the laptop. The drone logged:

```
rx rejects: ver=0 short=0 crc=3 len=0
```

So CRC-16/CCITT-FALSE validation, per-type length validation and rate-limited reject counters all work on real traffic. A valid SETPOINT incremented nothing, as expected.

---

## 6. Pin-assignment bugs — the project's recurring failure mode

Three bugs shipped this session **because code was never cross-checked against the netlist**. All three are fixed. Treat `firmware/companion-esp32s3/PINMAP.md` as authoritative and **check Kconfig defaults against PINMAP.md, not the other way round.**

| Function | Was | Now | Why the old value was wrong |
|---|---|---|---|
| FC UART TX/RX | 17/18 | **43/44** | 17/18 are camera data nets `D6`/`D7` |
| Servo | 21 | **42** | 21 is camera `HSYNC`. 42 = net `SRV_SIG`, pad 35 |
| I2S DOUT | 40 | **38** | swapped; see below |
| I2S DIN | 38 | **40** | swapped; see below |

**The I2S swap overheated the amplifier.** `KGN_I2S_DOUT=38` goes to U11 MAX98357A pin 1 (DIN). `KGN_I2S_DIN=40` comes from the INMP441's SD output on J2.

**The trap:** net names follow the *peripheral's* role, not the ESP32's. The net feeding the amp is called `/ESP32/DIN`; the net coming from the mic is called `SD`. Matching net names to `dout`/`din` gets both backwards.

### GPIO46 was mislabelled

It was `CONFIG_KGN_LCD_PMDN` and `display_spi.c` drove it as a "panel reset", leaving it HIGH. It is actually net `PMDN` → camera FPC1 pad 8 = the OV2640's **PWDN, active high**. So the firmware was holding the camera in power-down; the camera could never have worked. Now `CONFIG_KGN_CAM_PWDN`, owned by `camera_dvp.c` and passed as the driver's `pin_pwdn`.

The LCD's reset is J4 pad 11 on the **board-wide `RESET` net**, shared with SW1 pad 2 and the STM32 NRST. Consequences: **firmware cannot reset the panel**, and pressing SW1 resets the LCD, the STM32 and the ESP32 together. There is deliberately no LCD reset Kconfig option.

### BCLK/WS — CLOSED

Earlier notes warned that net labels `BCLK(38)` / `WS(39)` disagreed with the pads. The `(38)`/`(39)` are **stale label text from an older pin assignment, not copper**. Connectivity is unambiguous: **BCLK = 39** (pad 32), **WS = 41** (pad 34). No scope check needed. Any lingering "verify with a scope" guidance is obsolete.

---

## 7. Power tree — [NETLIST], matters for every bench session

| Rail | Regulator | Source |
|---|---|---|
| +3.3V | U6 | **VBUS** via diode D2 → USB-C powers 3.3 V |
| +5V | U7 LMR51430 | **VSYS**, and VSYS comes only from **+BATT** through fuse F1 |

**The 5 V rail exists only with the battery connected.** U7's EN is tied to VSYS, so it cannot be switched off.

| On 3.3 V (works on USB alone) | On 5 V (**battery required**) |
|---|---|
| ESP32 | ILI9341 display (J4 pin 14) |
| Camera: FPC1 pad 4 +3V3, pad 10 +1V2 (U10), pad 11 +2V8 (U8) | MG90S servo (J5 pin 1) |
| U11 MAX98357A amp | **RC receiver (J7 pin 4)** ← matters for the flight session |
| INMP441 mic | |

J1 pin 3 is NC, so the ESC provides **no BEC**. All 5 V comes from U7.

## 8. Connector map — [NETLIST], silkscreen values in backticks

| Conn | Pins |
|---|---|
| J1 ESC | 1 +BATT, 2 GND, 3 NC, 4 CURR, 5–8 M4..M1 |
| J2 `MIC_1` | SD, +3.3V, GND |
| J3 `MIC_2` | GND, WS, BCLK |
| J4 LCD (14-pin) | 7 LED, 8 LCD_SCK, 9 SDI (MOSI), 10 D/C, 11 RESET (board net), 12 LCD_CS, 13 GND, 14 +5V |
| J5 `SERVO` | +5V, GND, SRV_SIG |
| J6 `SPEAKER` | OUT+, OUT- |
| J7 RC | RC_TX, RC_RX, GND, +5V |
| FPC1 | 25-pin OV2640 camera |

**J2 and J3 together are one INMP441 breakout**, not two devices.

On-board, nothing to wire: **U11 = MAX98357A** I2S amp, **U5 = VL53L1X ToF** (on the STM32's I2C, so iNAV owns it — `rangefinder_hardware = VL53L1X`), **ICM-45686** gyro.

---

## 9. OPEN HARDWARE PROBLEM — where the session ended

The board gets **"really hot" near SW3** on USB power only (no battery), with the screen on J4, servo on J5, speaker on J6.

Battery out means U7 and the whole 5 V branch were unpowered — **the display and servo were not even powered**. That leaves two candidates, both ~8.5 mm from SW3:

| Candidate | Rail | Mechanism | Requires |
|---|---|---|---|
| **U11 MAX98357A** | 3.3 V | The DOUT/DIN swap left U11's data input floating while BCLK/WS kept running (TX channel was enabled at boot and never disabled, because the mic needed the clocks). A class-D amp that sees valid clocks does **not** enter no-clock shutdown, so it amplified noise into a 4 Ω load off 3.3 V. | the app **was** running |
| **U10 XC6206-1.2V** | 3.3 V → 1.2 V | In the bootloader GPIO46 is not driven high, so PWDN is low and the OV2640 is powered but unclocked. A SOT-23 LDO dropping 3.3→1.2 V at ~100 mA gets very hot and has **no thermal protection**. | the app was **not** running |

**Which branch applies was never determined.** Given the SW3/RTS trap above, "app not running" is entirely plausible.

Isolation procedure:

1. Power on USB with **J6 empty and FPC1 empty**.
2. Add one peripheral at a time.
3. Feel U11 vs U10.

Damage to check:

- Speaker voice coil — should read **3–4 Ω**; open = cooked.
- U11 — has thermal shutdown, decent survival odds.
- U10 — no thermal protection; confirm **+1V2 still reads 1.2 V**.
- ESP32 — almost certainly fine.

**Do not power up with the speaker or camera attached until the hot part is identified.**

### Speaker is gated off in firmware now — [BUILDS-ONLY]

New `CONFIG_KGN_AUDIO_TX_ENABLE`, default **n**:

- No I2S TX channel is allocated.
- GPIO38 is parked **LOW as a plain GPIO**, so U11 sees constant zeros instead of a floating input.
- The **RX channel becomes clock master**, so the mic still works.

`CONFIG_KGN_AUDIO_BOOT_TONE` default changed from y to **n**. `AUDIO_TTS` frames are accepted and discarded; `SELFTEST` logs a refusal.

Turn the gate on **only after GPIO38 is confirmed to reach U11 pin 1.**

---

## 10. Partition table — [HW-VERIFIED build size, flash pending]

`partitions.csv`:

| Name | Offset | Size |
|---|---|---|
| nvs | 0x9000 | 0x6000 |
| phy_init | 0xf000 | 0x1000 |
| factory (app) | 0x10000 | **0x300000 (3 MB)** |

`nvs` and `phy_init` did **not** move, so stored Wi-Fi/PHY calibration survives. Single factory app, **no OTA** — no OTA mechanism exists, flashing is over USB. ~12.9 MB of flash is unallocated after `factory`.

App is **1,004,016 bytes = 32 %** of 3 MB. The old 1 MB partition would have been 96 % full, so this was not optional.

**The next flash rewrites the partition table.**

---

## 11. Firmware written this session — [BUILDS-ONLY]

**No code path in this section has ever executed on the board.** All of it is in `firmware/companion-esp32s3/main/`.

### `telemetry.c` (new)
DRONE_STATE at 5 Hz + HEARTBEAT at 1 Hz to the base. Introduces a `KGN_DS_F_*` per-field validity bitmask on `drone_state.flags`. Only `LINKQ_VALID` is ever set today (Wi-Fi RSSI mapped -95→1, -35→100) because with no FC link, position/yaw/battery are genuinely unknown. Deliberately does **not** send zeros as if they were measurements.

### `servo_ledc.c`
Real angle control, verified LEDC maths, named RETRACTED/DEPLOYED positions, interpolated sweep, rate limiting, driven by MODE_CMD (FOLLOW and DOCK deploy the screen, everything else retracts).

**`CONFIG_KGN_SERVO_DEPLOYED_DEG = 110` is an invented placeholder.** Tune it with nothing attached before loading the mechanism, or the MG90S will stall against an end stop.

### `display_spi.c`
ILI9341 320x240 via `esp_lcd_new_panel_io_spi` plus a local init sequence (IDF 6.1 core has no ILI9341 panel driver; it lives in a separate managed component). No framebuffer — one 320x32 DMA band buffer. Built-in 5x7 font. Local status screen (name / IP / RSSI / uptime / mode / screen state / TX count) plus SCREEN_FRAME ingest.

MADCTL is **0x68**. If the image is mirrored or colour-swapped, that byte is the knob — try 0x28, 0xA8, 0xE8.

### `audio_i2s.c`
Full-duplex I2S on one controller. INMP441 capture with a documented 24→16-bit shift (`CONFIG_KGN_MIC_SHIFT` default 14) and an RMS/peak level log every 2 s for bench checking. MAX98357A playback (gated off, see §9). AUDIO_TTS ingest, CTRL commands. Mic streaming to the base is **off by default** on privacy and bandwidth grounds; enable with `AUDIO_TTS` fmt 2 cmd 1.

### `camera_dvp.c`
`espressif/esp32-camera` **2.1.7**. (2.1.1 is yanked upstream and fails to compile under IDF 6.1 — it does not declare `esp_driver_ledc` despite its header including it.) OV2640, VGA 640x480, JPEG quality 12, 2 PSRAM frame buffers, 15 fps cap. MJPEG at `/stream`, plus `/snapshot` and `/` status page. HTTP task priority 2, below everything.

**The HTTP server is unauthenticated — anyone who can route to the drone can watch the camera.**

### `wifi_udp.c`
CRC + per-type length validation on inbound; rate-limited reject counters; idempotent socket/task creation (the old code spawned a duplicate `udp_task` and leaked a socket on every reconnect); bounded exponential reconnect backoff with disconnect-reason logging; `WIFI_PS_NONE`.

### `PINMAP.md` (new)
`firmware/companion-esp32s3/PINMAP.md` — authoritative pad / GPIO / net map derived from the netlist, with the three pin bugs recorded as a warning.

---

## 12. Protocol — `firmware/shared/PROTOCOL.md` is current and authoritative

New this session:

- `drone_state.flags` per-field validity bitmask.
- `mode_cmd` → screen-mechanism mapping table.
- Full `screen_frame` (0x30) layout: 8-byte sub-header; `fmt=1` RGB565 tile; `fmt=2` TEXT line, 10 rows of 53 chars, 320x2 strips, 5 s panel reclaim.
- Full `audio_chunk` layout for 0x40 / 0x41: 4-byte sub-header; `fmt=1` PCM S16LE **16 kHz mono**; `fmt=2` CTRL with MIC_ON / MIC_OFF / SELFTEST / FLUSH.

Opus is explicitly **not** implemented.

---

## 13. Base station (Python) — 593 tests passing

Verified by execution against **loopback sockets**, never against the drone.

- Vision worker wired into `BaseStation` on a worker thread. Measured control-loop jitter stayed under **49 ms** against a 33 ms nominal while ~90 ms inference ran.
- Pose via `yolov8n-pose` with a beckon-gesture detector.
- FaceID via OpenCV `FaceDetectorYN` + `FaceRecognizerSF` (no mediapipe, no dlib), with enrolment and a JSON DB. Can override the tracker's `locked_id`.
- Floor-plane homography for fixed room cameras; the pinhole `MonocularEstimator` is kept as the drone-camera fallback.
- `StalenessMonitor` failsafe: stops commanding velocity and sends `HOLD` when measurements go stale. Matters because the FC failsafe is DROP.
- LD2450 serial decoder — **sign-magnitude, not two's complement**: bit 15 set means positive. Plus a `RadarWorker`.
- mmWave simulator.
- Screen senders for text / images / PIL panels.
- Audio senders for WAV / tone / CTRL, plus **Windows SAPI TTS via PowerShell with zero new pip dependencies**. AUDIO_MIC recorder.

CLIs: `kogane-base`, `kogane-cv`, `kogane-calibrate`, `kogane-mmwave-sim`, `kogane-screen`, `kogane-say`, `kogane-audio`.

All senders open their own socket, so the base station need not be running. They default to `CONFIG.drone_ip`, which is still **`192.168.4.2`** — pass `--host 10.28.43.18` or set `KGN_DRONE_IP`.

### No ESP32-C3 in the BOM

`firmware/mmwave-node-esp32c3/` has no hardware to run on. The BOM has one HLK-LD2450 and a USB-UART adapter, so the radar path is **LD2450 → USB-UART → laptop**, handled by the Python `tracking/radar.py`. Needs the `[radar]` extra (`pyserial==3.5`).

---

## 14. iNAV (already working — do not undo)

Built in WSL `~/inav` tag **9.1.0**, target MATEKF722.

1. `target_stm32f722xe(MATEKF722 HSE_MHZ 25)` — repo `firmware/fc-inav/patches/MATEKF722.CMakeLists.txt`
2. `system_stm32f7xx.c`: `PLL_M (HSE_VALUE / 1000000)` — `system_stm32f7xx-pllm.patch`
3. `target.h`: comment `VBUS_SENSING_*`. Gyro **ICM-45686** SPI1 CS **PA4**, INT PC4. No `USE_IMU_MPU6500`.
4. Motors: M1–M3 TIM2 CH1–3 PA0–PA2; **M4 TIM5 CH4 PA3 dmaopt 1**. Comment LED strip TIM2 CH1 PA15. `MATEKF722-motors-pa0-pa3.patch`

Hex: `~/inav/build/inav_9.1.0_MATEKF722.hex`. Flash Local, full chip erase, No reboot sequence. **Never Online**. DFU: hold SW2, tap SW1. Zadig WinUSB on **STM32 BOOTLOADER** VID 0483 PID DF11 only.

Do **not** paste all of `kogane-fc.diff`. Working CLI block (UART2/4 steal motor pins):

```
resource LED_STRIP 1 NONE
resource SERIAL_TX 2 NONE
resource SERIAL_RX 2 NONE
resource SERIAL_TX 4 NONE
resource SERIAL_RX 4 NONE
serial 1 0 115200 115200 0 115200
resource MOTOR 1 A00
resource MOTOR 2 A01
resource MOTOR 3 A02
resource MOTOR 4 A03
feature PWM_OUTPUT_ENABLE
set motor_pwm_protocol = DSHOT300
set failsafe_procedure = DROP
save
```

Gyro yaw: iNAV 9 uses `align_board_yaw` in decidegrees, not `align_gyro`. Fake ~9 V / 21 A ADC is a Matek pin mismatch. iNAV 9 motors live on **Outputs**. PSU ≥3 A to spin.

### MSP RC findings (verified in `~/inav`, no rebuild needed)

- `src/main/target/common.h:158` `#define USE_RX_MSP`, `:159` `#define USE_MSP_RC_OVERRIDE`. Both already default in this tree. A 2019 upstream PR saying otherwise is stale.
- `src/main/rx/msp.c:79` sets `rxRuntimeConfig->rxSignalTimeout = DELAY_5_HZ`; `src/main/rx/rx.h:50` defines `DELAY_5_HZ` as `1000000 / 5` µs = **200 ms**. `MSP_SET_RAW_RC` must be sent **faster than 5 Hz** or iNAV declares RC signal loss. `rx.h:96` `MAX_INVALID_RX_PULSE_TIME` = 300 ms.
- `rx.h:65` has `RX_TYPE_MSP`, so `feature RX_MSP` + `set receiver_type = MSP` is the path. The `BOXMSPRCOVERRIDE` overlay (`mspOverrideChannels`, `rx.h:129`) needs a real receiver underneath.
- With `failsafe_procedure = DROP`, a **>200 ms stall in the ESP32 is an in-air motor cut**. Props off.

### CLI verification checklist (paste before trusting the bridge)

```
get receiver_type
feature
get failsafe_procedure
get failsafe_delay
serial
map
status
```

Expect `receiver_type = MSP`, `RX_MSP` in `feature`, MSP enabled on the UART wired to PA9/PA10 at 115200, and `failsafe_procedure = DROP` recorded. Record `map` — the ESP32 RC channel order depends on it and **it has not been read back yet**.

### FC UART ownership on the ESP32 side

`CONFIG_KGN_FC_UART_TX/RX` = **43/44**. New Kconfig choice `KGN_UART0_PINS_OWNER` picks whether the IDF console or the FC link owns them. Console is default, so `link_fc_start()` logs a warning and returns, and `link_fc_apply_setpoint()` is a safe no-op:

```
W (…) link_fc: FC link disabled: IDF console owns GPIO43/44
```

That is correct output, not a regression. Note that with the console now on native USB the contention picture has changed, but the Kconfig default has not been revisited. Also: RXD0 (pad 36) is the destroyed castellation, so the FC link needs the **PA10 → IO3 rework** before it can work at all.

---

## 15. Flight strategy (radio arrives tomorrow)

**Fly on RC only.** CRSF into the STM32's UART3. Demo the companion's peripherals on the bench, separately.

**Do NOT attempt ESP32-controlled flight.** That would be a first flight with MSP as the receiver, a 200 ms iNAV timeout, DROP failsafe, and a control path that has never moved a motor. The project's own bring-up order puts ESP32 control at step 9, last.

Flight gate, in order, **props off until the last step**:

1. ELRS bind
2. Channel map (`map` in CLI)
3. Arming switch
4. **Failsafe verified on the bench**
5. Motor direction and order via Configurator
6. VBAT scale calibration (the ADC currently reads a fake ~9 V / 21 A)
7. First hover

**2.4 GHz coexistence:** if the radio module is 2.4 GHz ELRS it shares the band with the Wi-Fi link on channel 11, and ELRS hops across the whole band — it cannot be dodged by channel choice. Keep antennas apart. An RC dropout with DROP failsafe means motors stop.

---

## 16. Spec — awaiting review

`.kiro/specs/fc-msp-bridge/requirements.md` exists and is **awaiting review**: 8 requirements plus Non-Goals and 5 Open Questions. No `design.md`, no `tasks.md`.

Key open decisions:

- Link-loss behaviour: send neutral RC frames, or cease transmission and let iNAV's DROP failsafe fire.
- RC channel order, which depends on the iNAV `map` setting that **has never been read back**.
- Target setpoint rate.

---

## 17. Build environment — quirks that cost time

- IDF: `C:\esp\v6.1\esp-idf`. Tools: `C:\Users\sujay\.espressif`.
- Use **CMD**: `install.bat` then `export.bat`. PowerShell `export.ps1` is broken (empty `activate.py`).
- **Do not redirect `export.bat`'s stdout** — it breaks the script's internal `goto` labels.
- `build/` goes stale when the active python env differs from the one that configured it. Symptom is nonsense cmake errors; fix is `rm -r build/`.
- **OneDrive sync and concurrent git have locked `build/` repeatedly.** Retry, or pause sync.
- Project: `firmware/companion-esp32s3`, target esp32s3, 16 MB flash, octal PSRAM. `main/CMakeLists.txt` uses IDF 6 split drivers (`esp_driver_uart`, `esp_driver_ledc`).
- Do not pick Cursor OpenOCD on USB-JTAG. Firmware is IDF, not Arduino.
- `.gitignore` was created this session (the repo had none). `sdkconfig` is **ignored** because it holds the Wi-Fi password; `sdkconfig.defaults` is deliberately still tracked. Also ignores `firmware/*/build/`, `__pycache__/`, the venv, egg-info. Six `.pyc` files were committed before the rule existed and remain tracked.

Boot-log facts [HW-VERIFIED]: chip rev **v0.2**, 16 MB flash, octal PSRAM passed its test (**8 MB**, AP gen-3 die), station MAC **ac:27:6e:ab:56:d0**.

---

## Do not

- **Do not read net names as if they described the ESP32's role.** `/ESP32/DIN` feeds the amp; `SD` comes from the mic. This caused the I2S swap.
- **Do not power up with the speaker on J6** (or the camera on FPC1) until the hot part is identified.
- **Do not enable `KGN_AUDIO_TX_ENABLE`** before confirming GPIO38 physically reaches U11 pin 1.
- **Do not expect the display, servo or RC receiver to work without the battery** — they are all on the 5 V rail, which only exists via +BATT → F1 → VSYS → U7.
- **Do not attempt ESP32-controlled flight.**
- Do not assume SW3 is a download-mode button. On this board it is the opposite.
- Do not walk away after `esptool`; its RTS hard-reset lands in the bootloader with IO0 low.
- Do not type quotes into menuconfig string fields.
- Do not trust `link_fc` logs while the console owns GPIO43/44 — that build never touches the FC bus.
- Do not expect a UART0 fallback: the RXD0 castellation is destroyed. The USB bodge is the only path.
- Online MATEKF722 hex; full `kogane-fc.diff`; M4 on TIM2; `align_gyro`; flash the S3 from FC USB-C; Zadig on anything but STM32 BOOTLOADER; props / 4S hover before the flight gate.

---

## Next

1. **Identify the hot part** near SW3 (U11 vs U10) with the isolation procedure in §9. Everything peripheral is blocked on this.
2. **Flash the current build with SW3 taped down and confirm the boot log.** Nothing in §11 has ever run.
3. **R22 rework** — 10 k pulldown → pull-up on IO0, so the board boots unattended.
4. **PA10 → IO3 rework** for the FC link (RXD0 is destroyed).
5. **Tune the servo angles** with nothing attached; `DEPLOYED_DEG = 110` is a guess.
6. **Review `.kiro/specs/fc-msp-bridge/requirements.md`** and settle its 5 open questions.
7. **Flight gate** (§15) once the radio arrives — RC only.
