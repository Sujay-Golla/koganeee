# KOGANE FC — iNAV 9.x

The flight core runs **stock iNAV 9.x**. We do not write flight C code; we (a) pick/build
a target for the custom STM32F722RET6 board and (b) apply a CLI config
([`config/kogane-fc.diff`](config/kogane-fc.diff)).

Pin map source of truth: `hardware/DESIGN.md §5`. CubeMX `firmware.ioc` is a reference only.

---

## Option A — quickest: use a stock F722 target (recommended for bring-up)

The custom board's pinout closely matches common F7 layouts. For first power-on:

1. Put the board in DFU: **hold BOOT, tap RESET** (see `hardware/WIRING_GUIDE.md §7`).
2. In **iNAV Configurator**, flash a generic **`MATEKF722`** (or nearest F722) target.
3. Go to **CLI**, paste `config/kogane-fc.diff`, then `save`.
4. Verify in the **Setup** tab: ICM-45686 detected, accel ~1 g flat, gyro quiet.

> Resource remaps in the diff repoint motors/UARTs/SPI/I2C to the Kogane pins. Any pin the
> stock target can't remap is called out in the diff comments — that's when you need Option B.

## Option B — custom unified target (for a clean board definition)

Build iNAV from source with the Kogane target in [`target/`](target/):

```bash
git clone https://github.com/iNavFlight/inav.git && cd inav
git checkout release_9.x                       # match the release you fly
cp -r <repo>/firmware/fc-inav/target/KOGANEF722 src/main/target/
make TARGET=KOGANEF722                          # or: docker build per iNAV BUILD.md
```
Flash the resulting `.hex` via DFU, then apply the CLI diff.

`target/KOGANEF722/` here is a **skeleton** — `target.h`/`target.c`/`config.c` list the
Kogane resources with `TODO(kogane)` markers to reconcile against the current iNAV target API
(the target macro set changes between iNAV majors; check `docs/development/` in the iNAV tree).

---

## Files
```
fc-inav/
├─ README.md
├─ config/kogane-fc.diff     # CLI diff: resources, features, ports, failsafe
└─ target/KOGANEF722/        # custom unified-target skeleton
   ├─ target.h
   ├─ target.c
   └─ config.c
```

## Key config decisions baked into the diff
- **Gyro:** ICM-45686 on SPI1 (`USE_IMU_ICM45686`). Bench-verify — driver is new in 9.x.
- **Motors:** DShot300 on TIM2 CH1–4 (PA0–PA3). **Verify DShot DMA** — see DESIGN.md §5 note.
- **RC:** CRSF (ELRS) on UART3.
- **ESP32/MSP + MAVLink telemetry:** UART1. MSP override enabled for off-board setpoints.
- **Altitude:** VL53L1X rangefinder on I2C1.
- **Blackbox:** SDMMC (microSD).
- **Battery:** VBAT ADC on the divider; set `vbat_scale` after calibrating.
