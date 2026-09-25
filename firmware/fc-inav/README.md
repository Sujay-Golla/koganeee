# KOGANE FC — iNAV 9.x

The flight core runs **stock iNAV 9.x**. We do not write flight C code; we (a) pick/build
a target for the custom STM32F722RET6 board and (b) apply a CLI config
([`config/kogane-fc.diff`](config/kogane-fc.diff)).

Pin map source of truth: `hardware/DESIGN.md §5`. CubeMX `firmware.ioc` is a reference only.

This PCB uses a **25 MHz** HSE crystal (`YSX321SL-25MHZ`). Official MATEKF722 hexes
assume **8 MHz**. Flashing Configurator **Load Firmware [Online]** makes DFU succeed,
then USB vanishes after reset. That is the clock, not a dead chip. ROM DFU still works
(hold BOOT, plug USB).

---

## Option A — official MATEKF722 + 25 MHz clock (bring-up)

Same Matek target, plus two clock edits. CMake `HSE_MHZ 25` alone is **not**
enough: iNAV’s F7 startup hard-codes `PLL_M 8` (8 MHz). With a 25 MHz crystal
the MCU hangs in `SystemClock_Config` and USB disappears after reset. ROM DFU
still works. Do not pick another Online board. Do not use the `KOGANEF722`
skeleton yet.

### 1. Clone iNAV 9.1.0 (matches Configurator 9.1.1)

In **WSL** (iNAV’s recommended Windows path). Git for Windows is fine for the clone
if you then build inside WSL.

```bash
git clone https://github.com/iNavFlight/inav.git
cd inav
git checkout 9.1.0
```

### 2. Two clock edits in the iNAV tree

**A.** Overwrite iNAV’s Matek CMake file with
[`patches/MATEKF722.CMakeLists.txt`](patches/MATEKF722.CMakeLists.txt):

```
target_stm32f722xe(MATEKF722 HSE_MHZ 25)
```

```bash
cp "/mnt/c/Users/sujay/OneDrive/Documents/koganeee/firmware/fc-inav/patches/MATEKF722.CMakeLists.txt" \
   src/main/target/MATEKF722/CMakeLists.txt
```

**B.** In `src/main/target/system_stm32f7xx.c`, change the hard-coded divider:

```
#define PLL_M 8
```

to:

```
#define PLL_M (HSE_VALUE / 1000000)
```

Or apply [`patches/system_stm32f7xx-pllm.patch`](patches/system_stm32f7xx-pllm.patch)
from the `inav` directory:

```bash
git apply "/mnt/c/Users/sujay/OneDrive/Documents/koganeee/firmware/fc-inav/patches/system_stm32f7xx-pllm.patch"
```

Confirm both: CMakeLists has `HSE_MHZ 25`, and `PLL_M` is no longer the literal `8`.

### 3. Build

Install the packages from [Building in Linux](https://github.com/iNavFlight/inav/blob/master/docs/development/Building%20in%20Linux.md), then:

```bash
mkdir -p build && cd build
cmake ..
make -j$(nproc) MATEKF722
```

Hex lands in `inav/build/`, named like
`inav_9.1.0_MATEKF722.hex`.

Docker instead of apt: [Building in Docker](https://github.com/iNavFlight/inav/blob/master/docs/development/Building%20in%20Docker.md). Same checkout and both clock edits before you run the container.

### 4. Flash from Configurator (Local, not Online)

1. Board in DFU: hold **SW2** (BOOT), tap **SW1** (RESET), or unplug / hold BOOT / plug in.
2. Firmware Flasher: **DFU** selected. Tick **Full chip erase** and **No reboot sequence**.
3. **Load Firmware [Local]** → the `inav_9.1.0_MATEKF722.hex` you just built.
4. **Flash Firmware**. Wait for **Programming: SUCCESSFUL**.
5. Tap **SW1** (do not hold BOOT). A COM port should appear. **Connect**.

If Connect opens COM then errors with **No configuration received within 10 seconds**,
USB is working but Matek **VBUS sensing on PB12** is not on this PCB. iNAV then
ignores MSP. In `src/main/target/MATEKF722/target.h` comment out:

```
// #define VBUS_SENSING_PIN PB12
// #define VBUS_SENSING_ENABLED
```

Rebuild, Local-flash again, Connect. CLI still will not appear until that succeeds.

Then CLI: paste `config/kogane-fc.diff`, override `failsafe_procedure = DROP`, `save`.

ICM-45686 may still be missing on stock MATEKF722 — that is a target gap, not a reason
to connect a pack.

---

## Option B — custom unified target (not for first USB)

Build iNAV from source with the Kogane target in [`target/`](target/):

```bash
git clone https://github.com/iNavFlight/inav.git && cd inav
git checkout 9.1.0
cp -r <repo>/firmware/fc-inav/target/KOGANEF722 src/main/target/
# add a CMakeLists.txt in that folder: target_stm32f722xe(KOGANEF722 HSE_MHZ 25)
```

`target/KOGANEF722/` is a **skeleton** — `target.h`/`target.c`/`config.c` still have
`TODO(kogane)` markers. Do not use this until those are reconciled with the iNAV 9.1
target API.

---

## Files
```
fc-inav/
├─ README.md
├─ config/kogane-fc.diff              # CLI: resources, features, ports, failsafe
├─ patches/MATEKF722.CMakeLists.txt     # drop-in: official Matek target + 25 MHz HSE
├─ patches/system_stm32f7xx-pllm.patch  # PLL_M from HSE_VALUE (required or USB hangs)
└─ target/KOGANEF722/                 # custom unified-target skeleton (not first flash)
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
