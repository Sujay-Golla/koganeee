---
name: PCB Routing Guide
overview: "Create a thorough, beginner-friendly PCB routing guide (new ROUTING_GUIDE.md in hardware/FC/) for the KOGANE flight controller: a recommended board size/mounting + 4-layer stackup, a spatial floorplan, a step-by-step routing order, per-block best practices, and the specific KiCad features to set up and use."
todos:
  - id: write-guide
    content: Write hardware/FC/ROUTING_GUIDE.md with stackup, floorplan (mermaid), routing order, per-block best practices, KiCad feature setup, and pre-fab checklist, all tied to the parts/pin map in DESIGN.md
    status: completed
isProject: false
---

# PCB Routing Guide for the KOGANE FC

## Deliverable
A new markdown file [hardware/FC/ROUTING_GUIDE.md](hardware/FC/ROUTING_GUIDE.md), written for a routing beginner, that takes the design in [hardware/FC/DESIGN.md](hardware/FC/DESIGN.md) and [hardware/FC/WIRING_GUIDE.md](hardware/FC/WIRING_GUIDE.md) from "schematic done" to "ready to fab." The current `FC.kicad_pcb` is empty (no footprints, no board outline), so this guide covers layout from scratch.

It will be organized so the early sections (stackup, floorplan, ground) are the ones that, if done right, make everything else work — mirroring the tiered style of the existing wiring guide.

## What the guide will contain

### 1. Board form factor + mounting (my recommendation)
- Recommend ~**36x36 mm square, 4-layer**, with a **30.5x30.5 mm M3 mounting hole pattern** (industry-standard so it can stack with the 4-in-1 ESC, with corner soft-mount grommets). Rationale: dense part count (F722 LQFP-64 + ESP32-S3 module + 2 bucks + sensors) won't comfortably fit 30.5x30.5 outer, but keeping the standard hole pattern preserves mechanical compatibility and decouples vibration from the gyro.
- Note ESP32-S3 antenna keepout forces the module to a board edge, which anchors the floorplan.

### 2. Layer stackup (4-layer)
- **L1 Signal/components**, **L2 solid GND**, **L3 power (+3.3V / +5V / +3V3_G zones)**, **L4 Signal**.
- Why an unbroken L2 ground under L1 matters (return paths for SPI/USB/DShot), and the rule "never split the reference plane under a fast signal."
- JLCPCB-style default stackup numbers (trace width for impedance, prepreg) as a starting point.

### 3. Spatial floorplan (the "arrangement")
A zoned floorplan with a mermaid diagram placing each block:
- **Power-in corner**: XT30/VBAT pads, bulk cap, both LMR51430 bucks + inductors (keep switching loops tiny, away from gyro).
- **Gyro island**: ICM-45686 near board center / over a mounting hole, on `+3V3_G`, its LDO adjacent, isolated from buck switch nodes and the OV2640/DVP header.
- **MCU central**: F722 with crystals hugging PH0/PH1 and PC14/PC15, decoupling on the underside.
- **USB-C + USBLC6** on one edge near the MCU's PA11/PA12.
- **ESP32-S3** along an edge with antenna overhanging/keepout; payload harness headers (LCD/cam/mic/servo/audio) grouped near it.
- **Motor M1-M4 + RC UART headers** on the opposite edge from USB.
- **microSD** near the F722 SDMMC pins.

### 4. Routing order (do-this-first sequence)
1. Place + lock connectors/mounting holes and board outline.
2. Pour L2 ground; set up net classes.
3. Power: buck loops, then rail distribution on L3, stitching vias.
4. Critical signals: gyro SPI + INT, crystals, USB diff pair.
5. DShot motor lines, RC UART, I2C, SDMMC.
6. Remaining payload/IO, then ground stitching + cleanup.

### 5. Per-block best-practice rules (the bulk of the guide)
For each block: SPI gyro, both bucks, USB-C diff pair, crystals, DShot, SDMMC, I2C, ESP32/RF, audio, decoupling/vias, and the VBAT divider. Each gets concrete numbers (trace widths, via counts, clearances, keepouts) tied to this board's parts and the pin map in DESIGN.md section 5.
- Decoupling-cap placement rule (cap between via and pin), VCAP for F722.
- Buck "hot loop" minimization + ground the EP with a via array.
- USB ~90 ohm differential, length match, USBLC6 placement, no plane split under D+/D-.
- Crystal short symmetric traces + ground guard + no signals underneath.
- DShot: width for current, keep away from gyro, the TIM2 DMA note from DESIGN.md section 5.
- Gyro: own LDO, ferrite from +5V, quiet ground, mechanical placement for low vibration.
- Power trace width vs current (with a small ampacity reference table as a bullet list).

### 6. KiCad features to set up and use (specific, beginner-oriented)
- **Board Setup**: net classes (Power, USB_DIFF, DShot, Default) with per-class widths/clearances; differential pair naming for USB; design rules/constraints.
- **Stackup editor** for 4-layer + impedance.
- Tools: interactive router with "Highlight collisions," differential pair router, length tuning, copper zones/pours per layer, via stitching, the **DRC** + **"unconnected items"**, 3D viewer for mechanical checks, and the **net inspector**.
- Footprint/courtyard checks, edge clearance, and how to read DRC violations.

### 7. Pre-fab checklist
A final checklist (DRC clean, plane integrity, impedance, fab notes/stackup for JLCPCB, fiducials if assembled, silkscreen) building on the existing checklist in WIRING_GUIDE.md.

## Notes
- This is documentation only; no schematic/PCB edits will be made.
- All recommendations will reference the actual parts and pin map already locked in DESIGN.md, so the guide stays consistent with your design.