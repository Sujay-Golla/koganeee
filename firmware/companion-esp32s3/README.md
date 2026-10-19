# ESP32 companion

The ESP32-S3-WROOM-1-N16R8 handles Wi-Fi, the LCD, microphone capture, servo PWM and STM32 telemetry. The working prototype has demonstrated these paths on the bench. The onboard camera remains deferred, and the speaker amplifier needs a hardware repair.

## Build and flash

Use ESP-IDF 6.1 in its configured Command Prompt. Run from `firmware/companion-esp32s3`.

```bat
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p COM13 flash
idf.py -p COM13 monitor
```

Run `set-target` only on initial setup. Replace COM13 with the ESP32's native USB Serial/JTAG port. Exit the monitor with **Ctrl+]** before reflashing.

The module has 16 MB flash and 8 MB octal PSRAM. Keep the custom partition table and reserve GPIO35–37 for the module's memory.

## Boot and power

- Download mode needs IO0 low during reset. Normal boot needs IO0 high.
- The original reversed IO0 strap was repaired on the working board. Older instructions to hold SW3 for normal boot describe the unmodified PCB.
- The defaults disable automatic pre-flash reset. Enter download mode manually when needed.
- The LCD, servo and ELRS receiver use the battery-backed 5 V rail. USB alone does not power every peripheral.
- Check the [PCB notes](../../pcb/README.md) before powering a repaired or unverified board.

## Enable one stage at a time

The default image leaves all staged peripherals off. First verify boot, then enable each required stage in **Kogane Companion → Staged hardware bring-up**.

1. Enable Wi-Fi. Set the local SSID, password, laptop IPv4 and UDP port 5005.
2. Enable outbound telemetry and check reception on the laptop.
3. Enable the display and verify the physical panel.
4. Enable microphone capture with speaker TX and boot tone disabled.
5. Test servo PWM with the mechanism detached. Disable the boot sweep afterward.
6. Enable the FC link separately after checking its wiring.

Credentials belong in ignored `sdkconfig`. The [bring-up guide](BRINGUP.md) contains detailed checks and historical repair notes. Use the current boot behavior above when its older switch instructions differ.

## Flight-controller link

Select `KGN_PINS_OWNER_FC_LINK`, enable `KGN_BRINGUP_FC_LINK` and retain `KGN_FC_RX_ONLY=y`.

- STM32 PA9 TX connects to ESP32 GPIO43 RX.
- ESP32 GPIO44 TX connects to STM32 PA10 RX.
- Set iNAV UART1 to MAVLink at 115200 with MSP off on that UART.
- Keep `KGN_FC_REQUEST_TEST` off during normal use.

CRC-checked heartbeat and attitude reception, Wi-Fi forwarding and the bounded parameter-request test passed bench checks. Flight commands remain blocked. See [FC_LINK_CHECK.md](FC_LINK_CHECK.md).

## Payloads and source files

| File | Role |
| --- | --- |
| `main/wifi_udp.*` | Connects to Wi-Fi and exchanges KGN datagrams. |
| `main/link_fc.*` | Receives FC telemetry and gates the bench request test. |
| `main/display_spi.c` | Writes LCD cards to the ILI9341. |
| `main/audio_i2s.c` | Captures INMP441 audio at 16 kHz. |
| `main/servo_ledc.c` | Generates the servo PWM signal. |
| `main/camera_dvp.c` | Implements the optional OV2640 HTTP stream. |
| `main/kogane_msg.h` | Defines the companion's message structures. |

[PINMAP.md](PINMAP.md) records the physical connections. The LCD has no routed MISO or touch interface. Its reset is shared with the STM32. U11's grounded `SD_MODE` holds the speaker amplifier off, so the demo uses laptop audio output.

## Flash layout

The custom [partition table](partitions.csv) gives the application 3 MB. NVS and PHY data keep their original offsets. There are no OTA slots or filesystem partition.

| Partition | Offset | Size |
| --- | --- | --- |
| NVS | `0x9000` | 24 KB |
| PHY data | `0xf000` | 4 KB |
| Factory app | `0x10000` | 3 MB |

## Optional camera server

When the camera stage is enabled, the HTTP server provides `/`, `/snapshot` and `/stream` on port 80 by default. It has no authentication or TLS. Keep it on a trusted network. Camera software is present, but operation on the repaired board has not been established.

For the working assistant and mapping commands, use the [demo index](../Demo/INDEX.md).
