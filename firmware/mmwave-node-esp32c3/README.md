# KOGANE mmWave Node — ESP32-C3 (ESP-IDF)

One per HLK-LD2450. Reads the radar's tracked targets over UART and forwards them to the
laptop as `KGN` `MMWAVE_TARGETS` UDP datagrams. Deploy **2 nodes** in opposite room corners.

## Data path
```
LD2450  ──UART 256000──►  ESP32-C3  ──Wi-Fi UDP (KGN)──►  laptop (kogane_base)
```

## Build / flash
```powershell
idf.py set-target esp32c3
idf.py menuconfig     # Kogane Node -> Wi-Fi, base IP/port, node id, LD2450 UART pins
idf.py build
idf.py -p COM<x> flash monitor
```

## LD2450 frame format (implemented in `main/ld2450.c`)
Report frames: header `AA FF 03 00`, 3 targets × 8 bytes (x, y, speed, resolution),
footer `55 CC`. Coordinates are signed (sign bit in the high bit, mm units). See the
HLK-LD2450 serial protocol datasheet. `NODE_ID` (menuconfig) tags each node's datagrams
so the base can place them by corner.

## Status
`ld2450.c` parses frames from a byte stream; `wifi_udp.c` joins Wi-Fi and sends datagrams.
The `main.c` loop wires read → parse → send with `TODO(kogane)` markers for the decode math.
