# STM32 to ESP32 UART bench check

**Observed 2026-10-17:** receive-only firmware flashed; UART1 dedicated MAVLink
at 115200 produces increasing bytes, valid frames, heartbeat and attitude
counters with bad_crc=0. The microphone continues logging levels. The user
confirmed that tilting the board changes the attitude readings: the receive
test passes. Wi-Fi forwarding subsequently passed: 30 HEARTBEAT and 150
DRONE_STATE frames in 30 s, from ESP32 10.0.0.47, with flags=0x1e and a
numeric heading/FC voltage. Reverse transmission remains untested and blocked.

Both UART traces passed continuity on 2026-10-17. The PCB connects STM32
PA9 (USART1 TX) to ESP32 GPIO43, and PA10 (USART1 RX) to GPIO44.
ESP32 RX must be 43 and TX 44; old settings reversed these directions.

The prepared local sdkconfig selects FC_LINK ownership, BRINGUP_FC_LINK and
FC_RX_ONLY. RX_ONLY leaves GPIO44 as an input and drops SETPOINT requests.
USB logging stays active. The speaker TX path and completed servo sweep
are disabled. The original diagnostic only logged FC data; the step 4 build
also forwards fresh fields in DRONE_STATE.

## 1. Flash the diagnostic

Props off, battery disconnected, camera/servo/speaker disconnected.
Close any COM13 monitor with Ctrl+]. Connect ESP32 USB-C. In an ESP-IDF
6.1 terminal:

```powershell
cd "C:\Users\sujay\OneDrive\Documents\koganeee\firmware\companion-esp32s3"
idf.py -p COM13 flash monitor
```

Expected startup:

```text
FC RX-ONLY UART1: RX=GPIO43 @115200; TX=GPIO44 left INPUT; commands blocked
```

Every two seconds FC RX byte/frame counters print. Zero bytes are expected
until iNAV UART1 emits telemetry.

## 2. Configure iNAV UART1

Connect STM32 USB-C and open iNAV Configurator. Back up the current `diff all`
output. Exit CLI and open Ports. Set UART1 MSP off, Telemetry MAVLink with
baud 115200 (not AUTO), Serial RX off, sensors/peripherals disabled.
Keep UART3 Serial RX enabled for ELRS and keep USB MSP enabled.
Click Save and Reboot, then disconnect Configurator and inspect the ESP32
monitor. The dedicated telemetry port does not require arming.

## 3. Interpret the result

Pass: bytes, valid, heartbeat and attitude counters increase. Gently tilt the
unarmed board: logged roll/pitch should change. Sustained bad_crc growth
needs investigation. Skipped counts are normal for unsupported message IDs.
Bytes=0 means no traffic reached the selected RX input; bytes growing with
valid=0 means traffic arrived but protocol/framing needs checking.
Send several consecutive FC RX lines before changing more settings.

This checks STM32-to-ESP32 reception only. ESP32 transmission, MSP control,
FC telemetry forwarding and flight behavior remain unverified.
The small decoder supports CRC-checked MAVLink v1/v2 HEARTBEAT, SYS_STATUS and
ATTITUDE; signed or incompatible v2 messages and other IDs are skipped.
Its host test uses iNAV generated MAVLink headers to exercise fragmentation,
v2 truncation, corruption and recovery with memory/undefined-behavior checks.

## 4. Forward FC data to the laptop

The next prepared build fills the existing 12-byte DRONE_STATE with fresh FC
yaw, voltage, FC link and armed status. Position stays invalid. Roll/pitch
remain in the USB log. The ESP32 still leaves TX as an input and drops setpoints.
Only publish values whose message and heartbeat remain fresh: yaw 1 s,
heartbeat/voltage 3 s. Invalid values are zero with validity flags clear.

Flash this prepared build using the same command in step 1. Keep STM32 powered
and UART1 dedicated to MAVLink at 115200. In a second PowerShell window:

```powershell
cd "C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station"
.\.venv\Scripts\python.exe verify_wifi.py listen --seconds 30 --require-fc
```

Stop other listeners on UDP 5005 before running this passive monitor.
Expect FC=UP DISARMED and a numeric yaw. Rotate the unarmed board while keeping
it flat and check yaw changes on the laptop. Battery voltage is the FC's sensed
reading; unavailable data prints unknown. It may reflect USB power during this
battery-disconnected check. If Windows asks, allow this Python on the home
private network. No datagrams are sent by this listener.

Prepared build, host/loopback checks and actual Wi-Fi forwarding pass. The
configured destination matches the laptop's Wi-Fi address 10.0.0.66.

## 5. Physical loss/recovery check — passed

The user confirmed both loss and recovery on 2026-10-17: FC fields become
unavailable while companion heartbeats continue, then return when MAVLink
telemetry is restored. The procedure below is retained for repeat checks.

Run the passive listener for 90 s without --require-fc. In iNAV Ports, change
UART1 Telemetry to Disabled and Save and Reboot, keeping MSP off and UART3
Serial RX on. Within about 3 s FC=DOWN and unknown yaw/voltage should appear
while ESP32 Wi-Fi heartbeats continue. Restore UART1 MAVLink at 115200,
Save and Reboot, and verify FC=UP with heading/voltage again. Keep props off
and the FC unarmed. This tests telemetry validity only, not an RC failsafe.

## 6. Reverse UART read-request test — passed

The user reported attempt 1 at 2049 ms and a CRC-valid PARAM_VALUE reply/PASS
at 2073 ms. GPIO44 returned to input afterward. Both UART directions now pass
bench checks; flight commands remain blocked.

The local build enables KGN_FC_REQUEST_TEST while keeping KGN_FC_RX_ONLY on.
After a fresh disarmed FC heartbeat, it temporarily enables TX on GPIO44 and
sends MAVLink PARAM_REQUEST_LIST. iNAV 9.1.0 replies with PARAM_VALUE to report
an empty parameter list. The request does not write settings or RC channels.
No GCS heartbeat, arm message, mission message or RC override is sent.

At most three requests are sent, spaced by a 2 s reply timeout. A matching
CRC-valid reply passes. A missing disarmed FC heartbeat times out after 15 s.
On pass or failure GPIO44 returns to input. SETPOINT forwarding stays blocked.

Keep both USB connections powered, props off, battery disconnected and the FC
disarmed. UART1 stays dedicated MAVLink at 115200; disconnect Configurator.
Close the ESP32 monitor with Ctrl+] and run the step 1 flash/monitor command.
The test starts automatically. Look for:

```text
FC request test: PARAM_REQUEST_LIST attempt 1/3 -> sys=1 comp=1
FC request test PASS: CRC-valid PARAM_VALUE reply; TX=GPIO44 returned INPUT; flight commands blocked
```

Send the request test lines. A failure is inconclusive until the FC is confirmed
powered, disarmed and streaming telemetry; it does not itself prove a broken wire.
Host tests compare request bytes with generated MAVLink headers and check the
exact empty-list response, wrong-component rejection, retry limit and heartbeat gate.

## 7. Disarmed RC loss/recovery — passed

The user confirmed on 2026-10-17 that switching the RadioMaster Pocket off
produced the iNAV RC_LINK arming flag; switching it back on cleared that flag
and restored stick/channel response. Props were to be removed and the board
kept disarmed throughout, with battery/supply powering the ELRS receiver.

This verifies RC loss detection and recovery. Armed failsafe behavior, motor
outputs, motor order/direction and battery-voltage calibration remain unverified.
Before any motor test, read the current failsafe settings and inspect the ARM
mode/channel assignment.
