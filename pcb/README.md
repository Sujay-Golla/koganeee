# PCB notes

The flight-controller source is in [FC/](FC/). The saved design does not include every hand repair. These are known issues from netlist checks and bench tests, not a complete layout audit.

## Fixes for the next revision

| Issue | Fix |
| --- | --- |
| **Reversed ESP32 boot strap:** R22 pulls IO0 down; SW3 drives it high. | 10 kΩ pull-up and BOOT button to GND. The working prototype's IO0 was repaired. |
| **Floating ESP32 EN**, also connected to STM32 PB4. | Dedicated pull-up/reset timing; deliberately design any STM32 reset-control interface. Prototype has a hand-added pull-up. |
| **Native USB not routed** on GPIO19/20. | Proper connector, ESD protection and USB routing; remove fragile module-pad bodge wires. |
| **Speaker disabled:** U11 `SD_MODE` is grounded. | Correct amplifier enable/channel selection. Do not bridge the grounded pin to 3.3 V. |
| **Battery sensing absent:** PC0 is unconnected. | Dedicated filtered/protected ADC divider and test point; keep current sensing separate. Existing voltage/cell-count readings are invalid. |
| **Power ratings:** specified F1 is 16 V; Q2's VGS can exceed ±8 V. | Review for full 4S/LiHV voltage and transients; redesign source selection/gate protection and verify USB backfeeding. The fuse protects the FC branch, not ESC motor power. |
| **Connector mismatch and difficult rework.** | Match actual mating parts/pinouts; label pin 1; add test pads, tool clearance and strain relief. |
| **LCD/camera reset shared with STM32; no LCD MISO.** | Independent peripheral reset/power sequencing; route readback/touch signals if required. |
| **Stale labels / firmware assumptions.** | Synchronize pin map, I2S directions, 25 MHz clock, UARTs and motor timer/DMA assignments. Reserve N16R8 PSRAM pins. |

J1 ESC pin order is **+BATT, GND, NC, CURR, M4, M3, M2, M1**. Verify the replacement harness electrically; matching housings do not guarantee matching pinouts. LCD/servo/receiver need the battery-backed 5 V rail; consider a protected bench input and labelled rail test points.

## Unresolved physical faults

One repaired FC has a suspected VSYS-to-GND short and no normal regulated rails. The faulty part has **not** been identified; do not assume D4, Q2, U7 or the old ESC is confirmed failed. Keep that board unpowered until isolated. Damaged UART pads and solder bridges are assembly/rework faults, separate from the design errors above.

Before ordering: reconcile BOM values/supplier IDs, regenerate ERC/DRC (the saved report is historical), check connector drawings and firmware mapping, then verify power selection and loads on the new board.

Details: [firmware setup and hardware notes](../firmware/README.md), [pin map](../firmware/companion-esp32s3/PINMAP.md), [power review](../firmware/fc-inav/POWER_REVIEW.md), [battery sensing](../firmware/fc-inav/BATTERY_SENSE_CHECK.md).
