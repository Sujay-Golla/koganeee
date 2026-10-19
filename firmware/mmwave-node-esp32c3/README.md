# Optional ESP32-C3 radar node

This firmware reads an HLK-LD2450 over UART and forwards target reports to the laptop as KGN UDP datagrams. It is an alternative to the direct USB-UART connection used in the current demo.

## Data path

```text
LD2450 → UART at 256000 baud → ESP32-C3 → Wi-Fi UDP → laptop
```

## Wiring and configuration

- Power the LD2450 from a suitable 5 V source and connect its ground to the ESP32-C3 ground.
- Use compatible 3.3 V UART logic. Connect radar TX to the configured ESP32 RX pin.
- If command transmission is required, connect ESP32 TX to radar RX.
- In menuconfig, set the Wi-Fi credentials, laptop IPv4, UDP port, node ID and actual UART pins.
- Give each node a distinct ID and configure its physical position in the laptop's room transform.

The default UART pins are GPIO5 RX and GPIO4 TX. Check them against the chosen development board before wiring.

## Build and flash

Use an ESP-IDF terminal from `firmware/mmwave-node-esp32c3`. Replace COM6 with the node's actual port.

```bat
idf.py set-target esp32c3
idf.py menuconfig
idf.py build
idf.py -p COM6 flash monitor
```

## Implementation and status

`main/ld2450.c` parses 30-byte reports with header `AA FF 03 00`, three target records and footer `55 CC`. Coordinates and speed use sign-magnitude encoding. `wifi_udp.c` sends the resulting reports using the node ID.

This optional node has not been demonstrated on physical C3 hardware in the current build. For the working radar setup, follow the [USB-UART room-mapping guide](../Demo/ROOM_MAPPING_DEMO.md). Message definitions are in [PROTOCOL.md](../shared/PROTOCOL.md).
