# Repaired ESP32-S3 board: staged bring-up

**2026-10-17 speaker finding:** U11 pin 4 `SD_MODE` is tied to GND in the
PCB and was confirmed continuous to GND on the repaired board. LOW forces
the MAX98357A into shutdown. The ESP32 can initialize I2S TX/RX and log a
self-test while J6 stays silent. Do not jumper pin 4 to 3.3 V until its GND
connection is physically isolated. See `PINMAP.md`.

This procedure starts with the replacement ESP32-S3-WROOM-1-N16R8 on the
repaired flight controller. COM13 is the reported port; confirm that it is the
ESP32 USB Serial/JTAG device (VID 303A, PID 1001) before flashing. The old
COM11 and damaged RXD0 notes in `HANDOFF.md` describe the previous module.

## Before the first flash

1. Remove propellers. Leave the battery disconnected. Unplug J6 speaker, FPC1
   camera, J4 display, and J5 servo. Disconnect the RC receiver if attached.
2. Use only the ESP32 USB-C connection. Check that the board does not heat up
   on USB alone. If it does, disconnect USB and identify the hot component
   before proceeding. The prior board overheated near SW3; U11 (audio amp)
   versus U10 (camera 1.2 V regulator) was never isolated.
3. Confirm the replacement module is N16R8 (16 MB flash, 8 MB octal PSRAM).
   Do not substitute GPIO35/36/37 for damaged pads; octal PSRAM uses them.
4. IO0 is still pulled LOW by R22. SW3 held HIGH makes the app boot; SW3
   released makes a reset enter the ROM downloader. This is the inverse of
   the usual boot-button convention. Do not rework R22 during this sequence.

## First image: ESP32 boot and NVS only

Use **Command Prompt**, not PowerShell, for the installed ESP-IDF environment:

```bat
cd /d C:\Users\sujay\OneDrive\Documents\koganeee\firmware\companion-esp32s3
call C:\esp\v6.1\esp-idf\export.bat
idf.py menuconfig
idf.py build
idf.py -p COM13 flash
idf.py -p COM13 monitor
```

In menuconfig, leave everything under **Kogane Companion → Staged hardware
bring-up** unchecked. Leave `KGN_AUDIO_TX_ENABLE` and `KGN_AUDIO_BOOT_TONE`
unchecked, and leave the FC UART pins reserved. The local `sdkconfig` holds
Wi-Fi credentials and is ignored by Git. Do not type quote marks into a
menuconfig string field.

For flashing, **release SW3** and reset/reconnect the board so IO0 is LOW and
the ESP32 is in ROM download mode. `CONFIG_ESPTOOLPY_BEFORE_NORESET=y` is set.
After flashing, keep the serial monitor open, **hold SW3 and tap SW1** to reset
into the app. Release SW3 after the boot log starts. On every later reset,
repeat the SW3 hold until R22 is changed to a pull-up. An `esptool` final
"Hard resetting via RTS" while SW3 is released puts the chip back in the ROM
downloader; a quiet log after flash does not prove a firmware hang.

Expected result: boot log, PSRAM test, `Kogane companion boot`, then
`selected bring-up subsystems started`. No Wi-Fi or peripheral task should
start. Exit the monitor with `Ctrl+]`. Record the COM port, chip revision,
flash size, PSRAM size, 3.3 V rail, and whether any component becomes warm.
Do not use `erase-flash`: the normal flash action writes the bootloader,
partition table, and app while preserving the NVS/PHY partition locations.

## Add exactly one stage per build

For each row, change only the named menuconfig switch, run `idf.py build`,
flash with SW3 released, boot with SW3 held while tapping SW1, and inspect the
monitor before proceeding. Keep earlier proven stages enabled unless isolating
a fault. Stop and disconnect power if a regulator or IC becomes hot.

| Stage | Enable / attach | Check before advancing |
|---|---|---|
| 1. Wi-Fi | `KGN_BRINGUP_WIFI`; set SSID, password, base IP | Association, DHCP IP, no reboot loop; use a 2.4 GHz network. |
| 2. Telemetry | `KGN_BRINGUP_TELEMETRY` | HEARTBEAT at 1 Hz and DRONE_STATE at 5 Hz received by the laptop; only valid fields should be trusted. |
| 3. Microphone | Attach the one INMP441 breakout across J2 and J3; `KGN_BRINGUP_AUDIO`, with `KGN_AUDIO_TX_ENABLE=n` and J6 empty | RMS/peak log changes when clapping. GPIO38 (amp DIN) stays LOW; U11 must remain cool. Flip `KGN_AUDIO_SLOT_RIGHT` only if data stays constant. |
| 4. Camera | With power off, confirm U10's +1V2 rail; attach FPC1, then `KGN_BRINGUP_CAMERA` | Sensor probe succeeds, `/snapshot` returns JPEG, U10 remains at 1.2 V and does not overheat. Camera HTTP has no authentication; use an isolated bench network. |
| 5. Display | Attach J4 with power off; verify +5 V from the battery-backed rail, then `KGN_BRINGUP_DISPLAY` | Status page visible, no reset loop, no abnormal current or heat. USB alone does not power J4 +5 V. |
| 6. Servo | Leave the mechanism detached. Attach J5 with power off; `KGN_BRINGUP_SERVO` | Boot parks at `RETRACTED_DEG`; command a small travel only after measuring safe angles. The default `DEPLOYED_DEG=110` is a guess. J5 needs +5 V. |
| 7. Speaker | **Blocked by hardware:** U11 pin 4 `SD_MODE` is grounded. Isolate and repair that QFN connection, or use an external I2S amplifier; keep J6 disconnected from an external amp's output. | Only after the enable path is fixed, run a deliberate low-amplitude self-test and check for heat. Leave the boot tone off. |

### Home Wi-Fi: stages 1 and 2 in detail

The ESP32-S3 joins **2.4 GHz** Wi-Fi. A dual-band home SSID is fine if it
actually offers a 2.4 GHz network. Put the laptop on the same reachable home
LAN (Wi-Fi or Ethernet), not a client-isolated guest network. In Command Prompt,
run `ipconfig` and find the laptop's IPv4 address for that LAN adapter. This is
`KGN_BASE_IP`; it is **not** the router/default gateway address. The firmware
uses an IPv4 literal, not a hostname. A DHCP change to the laptop address will
require updating and reflashing this setting before telemetry works again.

For **stage 1**, run `idf.py menuconfig` and set:

- `Kogane Companion → Staged hardware bring-up → Start Wi-Fi and UDP` = enabled.
- `Kogane Companion → Wi-Fi SSID` = your home SSID, as bare text.
- `Kogane Companion → Wi-Fi password` = enter locally; do not put it in
  `sdkconfig.defaults`, a screenshot, or a message. The generated `sdkconfig`
  is ignored by Git.
- `Kogane Companion → Base station (laptop) IP` = the laptop's home-LAN IPv4.
- UDP port = `5005`; leave telemetry, FC link, and all physical peripherals off.

Save menuconfig, then run `idf.py build`, `idf.py -p COM13 flash`, and
`idf.py -p COM13 monitor`. Flash with SW3 released; after flashing hold SW3 and
tap SW1 to boot the app. Look for `wifi starting (power save disabled)` and
`got IP <drone-ip>, opening UDP socket`. Write down `<drone-ip>`; do not reuse
the old hotspot address `10.28.43.18`. On the laptop, `ping <drone-ip>` is a
quick reachability check, but the UDP check below is stronger:

```bat
cd /d C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.venv\Scripts\python.exe verify_wifi.py probe --host <drone-ip>
```

Run the probe while the ESP32 monitor is open in another terminal. It sends
two deliberately bad-CRC HEARTBEAT frames, more than five seconds apart; it
never sends a control command. The monitor should print `rx rejects` with
`crc=2`. If the ESP32 gets an IP but the probe is not counted, check that
laptop and drone can reach each other, the printed DHCP address, UDP/5005,
and guest-network isolation. If it repeatedly disconnects, record the logged
reason and recheck the SSID/password and 2.4 GHz availability.

For **stage 2**, enable only `Start outbound telemetry` in menuconfig. Rebuild,
flash, and boot the same way. Confirm the monitor prints `telemetry task:
DRONE_STATE 5 Hz, HEARTBEAT 1 Hz -> <laptop-ip>:5005`. With the full base
station **stopped**, run this receive-only check on the laptop:

```bat
cd /d C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.venv\Scripts\python.exe verify_wifi.py listen --seconds 10
```

Expect roughly 10 HEARTBEAT and 50 DRONE_STATE frames in ten seconds, from
the drone's new home-LAN IP. At this stage `DRONE_STATE` should report Wi-Fi
link quality as valid, with position, yaw, battery, and FC link still invalid.
If the ESP32 logs telemetry but the laptop receives none, check `KGN_BASE_IP`,
Windows Firewall permission for Python on the private network, UDP/5005, and
whether another base-station process already owns the port. The normal base
station still defaults to drone IP `192.168.4.2`; later, set `KGN_DRONE_IP`
to the new drone IP or let it learn the address from telemetry once received.

The STM32/iNAV flight path is a separate project track. `KGN_BRINGUP_FC_LINK`
stays off throughout this list, even though the ESP32 pad has been repaired:
GPIO43/44 continuity and the FC UART protocol have not been verified, and the
current bridge contains placeholder control and MAVLink parsing. Do not use it
for flight. The STM32 image is not affected by an ESP32 flash through COM13.
