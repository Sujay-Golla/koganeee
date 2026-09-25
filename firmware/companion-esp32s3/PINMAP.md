# Kogane companion (ESP32-S3-WROOM-1-N16R8) pin map

**Source of truth.** Every row below is derived from the PCB netlist — the U4
pad -> net map read out of `pcb/FC/jlcpcb/gerber/FC-CuTop.gbr`. The copper is
authoritative. Kconfig defaults in `main/Kconfig.projbuild` must be checked
against this file, not the other way round.

## Why this file exists

Three separate pin-assignment bugs shipped because nobody cross-checked code
against the netlist:

- The FC UART was assigned to GPIO17/18. Those pads are camera data nets
  **D6/D7**.
- The servo was assigned to GPIO21. That pad is camera **HSYNC** (`HS`).
- **The two I2S data pins were swapped, and it cooked the amplifier.**
  `CONFIG_KGN_I2S_DOUT` was 40 and `CONFIG_KGN_I2S_DIN` was 38 — exactly
  inverted. The correct assignment is **DOUT = 38** (to U11, the MAX98357A) and
  **DIN = 40** (from the INMP441 on J2). This is the most damaging of the three
  and the only one with a thermal consequence: with DOUT on the wrong pin,
  nothing drove U11 pin 1, so the amp's data input floated — but `audio_i2s.c`
  enabled the I2S TX channel at boot and deliberately never disabled it (BCLK/WS
  came from the TX side and the microphone needed them). A class-D amp that sees
  valid clocks does not enter its no-clock shutdown, so U11 stayed on and
  amplified noise into a 4 ohm load off 3.3V. Reported symptom: the board getting
  **really hot near SW3** on USB power alone with a speaker plugged into J6. The
  same swap also configured GPIO40 as an I2S output into the microphone's data
  output, so with the mic connected two drivers fought over that net. See the
  Audio section below; the speaker path is now gated off by default.

All three looked fine in isolation and all three were wrong. If you add a driver,
find the pin here first. Reading a net *name* as if it described the ESP32's role
is how the third one happened — see the Audio section.

## Hard constraints

### Never use IO35 / IO36 / IO37

This is the **N16R8** module: 8 MB **octal** PSRAM, which consumes GPIO33-37
internally. The PCB leaves pads 28/29/30 (IO35/36/37) unconnected, which makes
them look like free GPIO on the board. They are not free. Using them corrupts
PSRAM access.

### RXD0 castellation is destroyed

Module pad 36 (GPIO44, net `ESP32-RX`, from STM32 PA10) is physically broken on
the current board. Consequences:

- The board flashes and logs over **native USB** (USB-Serial-JTAG,
  VID_303A / PID_1001, enumerated on COM11, full boot log captured) via a USB
  breakout hand-soldered to module pads 13/14 — see "USB bodge wire on pads
  13/14" below. The IDF console is configured for USB-Serial-JTAG, not UART0.
- The FC link can transmit to the STM32 but **cannot receive**, so it stays
  disabled: `CONFIG_KGN_PINS_OWNER_CONSOLE=y`.
- **Pending rework:** wire STM32 **PA10 -> module pad 15 (IO3)**, which is
  currently unconnected. After that rework, set `CONFIG_KGN_FC_UART_RX=3` and
  `CONFIG_KGN_PINS_OWNER_FC_LINK=y`.

## Pad / GPIO / net table

### Flight-controller link

| Pad | GPIO | Net | Function |
|-----|------|-----|----------|
| 37 | 43 (TXD0) | `ESP32-TX` | ESP32 TX -> STM32F722 PA9 |
| 36 | 44 (RXD0) | `ESP32-RX` | ESP32 RX <- STM32F722 PA10 — **pad destroyed** |

### Servo

| Pad | GPIO | Net | Function |
|-----|------|-----|----------|
| 35 | 42 | `SRV_SIG` | MG90S servo signal (LEDC) |

### Display (SPI LCD — ILI9341 320x240)

The BOM part is an **ILI9341 2.8" SPI touch display**, 320x240. Earlier notes in
this project called it "ST7789-class"; that was wrong. The driver in
`main/display_spi.c` targets ILI9341.

| Pad | GPIO | Net | Function |
|-----|------|-----|----------|
| 18 | 10 | `LCD_CS` | chip select |
| 20 | 12 | `LCD_SCK` | SPI clock |
| 19 | 11 | `SDI` | SPI MOSI (panel side) |
| 17 | 9 | `D/C` | data / command |
| 12 | 8 | `LED` | backlight |

> **The panel reset is not a GPIO.** J4 pad 11 is the board-wide **`RESET`** net,
> shared with SW1 pad 2, C25 and the STM32F722's NRST (U1 pad 7). Nothing the
> ESP32 drives reaches it. The LCD is reset at power-on and whenever **SW1 is
> pressed** — which resets the STM32 and the ESP32 at the same time, so firmware
> never observes it. There is deliberately no `CONFIG_KGN_LCD_*` reset option.
>
> An earlier revision of this table listed **pad 16 / GPIO46 / `PMDN`** as the
> panel reset and `display_spi.c` drove it as one. That was wrong twice over:
> GPIO46 does not go to J4, and it *is* the camera's power-down input, so parking
> it high held the OV2640 off. GPIO46 is now in the camera section below.

Full J4 pinout, for reference when the ribbon is reseated: pad 7 `LED`,
pad 8 `LCD_SCK`, pad 9 `SDI` (MOSI), pad 10 `D/C`, pad 11 `RESET` (board net),
pad 12 `LCD_CS`, pad 13 GND, pad 14 **+5V**.

> **No MISO.** The PCB routes `SDI` only — there is no panel-to-MCU data line.
> The ILI9341 ID registers therefore cannot be read back, so firmware has no way
> to detect an absent or unresponsive panel. A dead panel looks identical to a
> working one from the host side.

### Audio (I2S)

Shared clocks, two data lines, two parts: **U11** (MAX98357A amplifier, on-board)
and the **INMP441** microphone breakout on **J2 + J3**.

| Pad | GPIO | Net | Function |
|-----|------|-----|----------|
| 32 | 39 | `BCLK(38)` | bit clock — shared by U11 pin 16 and J3 |
| 34 | 41 | `WS(39)` | word select / LRCLK — shared by U11 pin 14 and J3 |
| 31 | 38 | `/ESP32/DIN` | **ESP32 data OUT** -> U11 pin 1 (amp DIN) |
| 33 | 40 | `SD` | **ESP32 data IN** <- J2 pin 1 (INMP441 SD) |

#### Speaker: U11 (MAX98357A) on GPIO38, output on J6

| Part / pin | Net | Goes to |
|------------|-----|---------|
| U4 pad 31 = **GPIO38** | `/ESP32/DIN` | U11 pin 1 `DIN` — the amp's serial-data **input** |
| U11 pin 16 `BCLK` | `BCLK(38)` | U4 pad 32 = GPIO39 |
| U11 pin 14 `LRCLK` | `WS(39)` | U4 pad 34 = GPIO41 |
| U11 pin 7 `VDD` | `+3.3V` | board 3V3 rail |
| U11 pins 9 / 10 `OUTP` / `OUTN` | `OUT+` / `OUT-` | **J6**, silkscreen `SPEAKER` |

`CONFIG_KGN_I2S_DOUT = 38`.

#### Microphone: INMP441 on J2 (`MIC_1`) + J3 (`MIC_2`), data in on GPIO40

| Connector | Net | Goes to |
|-----------|-----|---------|
| J2 pin 1 | `SD` | U4 pad 33 = **GPIO40** — the INMP441's serial-data **output** |
| J2 (other pins) | `+3.3V`, `GND` | mic power |
| J3 | `GND`, `WS(39)`, `BCLK(38)` | shared clocks |

`CONFIG_KGN_I2S_DIN = 40`. J2 and J3 together are one microphone breakout, not
two devices.

> **Net names here do not follow I2S roles, and that is the trap.** The net that
> feeds the *amplifier* is called `DIN` because it is the amp's input, and the net
> that comes *from the microphone* is called `SD`. Matching those names to the
> ESP32's `dout`/`din` gets both pins backwards. Only connectivity decides.

> **BCLK and WS are settled — no bench verification needed.** The `(38)` and
> `(39)` in the net names `BCLK(38)` / `WS(39)` are **stale labels left over from
> an earlier pin assignment**. They are text in the schematic, not copper.
> Connectivity is unambiguous: the bit clock lands on U4 pad 32 (IO39) and word
> select on U4 pad 34 (IO41). **BCLK = 39, WS = 41.** Earlier revisions of this
> file carried a "verify BCLK and WS before trusting them" warning and a scope
> procedure for telling a clock swap apart from a dead part; that question is
> closed and the procedure has been removed.

#### The speaker is gated off by default

`CONFIG_KGN_AUDIO_TX_ENABLE` defaults to **n** and `CONFIG_KGN_AUDIO_BOOT_TONE`
defaults to **n**. With the gate off, `main/audio_i2s.c` allocates no I2S TX
channel, drives GPIO38 LOW as a plain GPIO so U11 sees constant zero samples
instead of a floating input, and brings the **RX channel up as the clock master**
so the microphone still gets BCLK/WS. Playback traffic is still accepted and
discarded, and a `SELFTEST` command logs that the path is disabled.

Turn the gate on once GPIO38 has been confirmed to reach U11 pin 1, then fire the
tone deliberately with `AUDIO_TTS` fmt 2 cmd 3.

Note that nothing about either part can be settled from the host side in
firmware. I2S has no readback: an absent mic, a miswired mic and a working mic
are identical to the ESP32, exactly as the missing panel MISO makes a dead LCD
undetectable. The INMP441's L/R strap is still an open unknown — if the mic reads
as a dead constant, flip `CONFIG_KGN_AUDIO_SLOT_RIGHT` and retry; that is one
config change and a reflash.

### I2C

| Pad | GPIO | Net |
|-----|------|-----|
| 24 | 47 | `SDA` |
| 25 | 48 | `SCL` |

### Camera (DVP)

| Pad | GPIO | Net | Function |
|-----|------|-----|----------|
| 21 | 13 | `PCLK` | pixel clock |
| 22 | 14 | `MCLK` | master clock (sensor XCLK) |
| 26 | 45 | `VS` | VSYNC |
| 23 | 21 | `HS` | HSYNC — the pad the servo default used to squat on |
| 24 | 47 | `SDA` | SCCB data (shared I2C, FPC1 pad 3) |
| 25 | 48 | `SCL` | SCCB clock (shared I2C, FPC1 pad 5) |
| 16 | 46 | `PMDN` | **OV2640 PWDN** (FPC1 pad 8) — `CONFIG_KGN_CAM_PWDN` |

**GPIO46 / `PMDN` is the camera's power-down, not a display line.** The net runs
from module pad 16 to camera FPC1 pad 8 and nowhere else. It is **active high**,
so the sensor only runs with the line LOW; the esp32-camera driver pulses it high
then low during `camera_probe()` and leaves it low, so `camera_dvp.c` passes it as
`pin_pwdn` and never touches it directly. `display_spi.c` previously claimed this
pin as `CONFIG_KGN_LCD_PMDN` and left it HIGH, which held the camera off — see the
display section above.

**There is no ESP32-controllable camera reset.** FPC1 pad 6 goes to the board-wide
`RESET` net (SW1 / STM32 NRST / J4 pad 11), so `CONFIG_KGN_CAM_RESET = -1` and the
driver falls back to a software reset over SCCB. A sensor too wedged to answer
SCCB needs SW1 or a power cycle.

**Camera power rails come off 3.3V**, so the module runs on USB power alone: FPC1
pad 4 is +3V3, pad 10 is +1V2 (U10), pad 11 is +2V8 (U8), both derived from 3.3V.

Camera data bus:

| Net | GPIO |
|-----|------|
| D0 | 4 |
| D1 | 5 |
| D2 | 6 |
| D3 | 15 |
| D4 | 7 |
| D5 | 16 |
| D6 | 17 |
| D7 | 18 |
| D8 | 1 |
| D9 | 2 |

### Unconnected module pads

| Pad | GPIO | Note |
|-----|------|------|
| 13 | 19 (USB_D-) | **not free — USB bodge wire, see below** |
| 14 | 20 (USB_D+) | **not free — USB bodge wire, see below** |
| 15 | 3 | unconnected — **target of the PA10 rework** |
| 28 | 35 | unconnected but **reserved by octal PSRAM — do not use** |
| 29 | 36 | unconnected but **reserved by octal PSRAM — do not use** |
| 30 | 37 | unconnected but **reserved by octal PSRAM — do not use** |

### USB bodge wire on pads 13/14

The netlist shows pads 13/14 (IO19/IO20, the native USB D-/D+ pair) as
unconnected because the PCB never routed them. A USB breakout was **hand-soldered
directly to those two castellations** after the UART RXD0 pad was destroyed,
which left native USB as the only way to flash and log the board.

Consequences:

- Native USB (USB-Serial-JTAG) **is the console and the flash path**. The board
  enumerates as VID_303A / PID_1001; `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`.
- Pads 13/14 are **in use and not available as GPIO**, despite what the copper
  says. Assigning a peripheral to IO19/IO20 breaks the only console on the board.
- The wires are mechanical: they are the most likely thing to fail if the board
  is handled, and a "dead board" should be checked here first.

This is a known, deliberate bodge, not an unexplained netlist discrepancy.
Nothing needs tracing.
