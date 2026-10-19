# PCB notes

The flight-controller source is in [FC/](FC/). The saved design does not include every hand repair. These are known issues from netlist checks and bench tests, not a complete layout audit.

## Fixes for the next revision

| Issue | Fix |
| --- | --- |
| **Reversed ESP32 boot:** Currently R22 pulls IO0 down and SW3 drives it high (need to hold it if you want to flash the ESP32), so add a 10 kΩ pull-up and BOOT button to GND. |
| **Floating ESP32 EN**, also connected to STM32 PB4. | Dedicated pull-up/reset timing; deliberately design any STM32 reset-control interface. Prototype has a hand-added pull-up. |
| **Native USB not routed** on GPIO19/20 for ESP32. | Proper connector, ESD protection and USB routing |
| **Speaker disabled:** U11 `SD_MODE` is grounded. | Correct amplifier enable/channel selection. Do not bridge the grounded pin to 3.3 V. |
| **Battery sensing absent:** PC0 is unconnected. | Dedicated filtered/protected ADC divider and test point |
| **Power ratings:** specified F1 is 16 V; Q2's VGS can exceed ±8 V. | Review for full 4S/LiHV voltage and transients; redesign source selection/gate protection and verify USB backfeeding. The fuse protects the FC branch, not ESC motor power. |
| **Connector mismatch and difficult rework.** | Match actual mating parts/pinouts, label pin 1, add test pads, tool clearance and strain relief. |
| **LCD/camera reset shared with STM32; no LCD MISO.** | Independent peripheral reset/power sequencing. |
| **Stale labels / firmware assumptions.** | Synchronize pin map, I2S directions, 25 MHz clock, UARTs and motor timer/DMA assignments. Reserve N16R8 PSRAM pins. |

Details: [firmware setup and hardware notes](../firmware/README.md), [pin map](../firmware/companion-esp32s3/PINMAP.md), [power review](../firmware/fc-inav/POWER_REVIEW.md), [battery sensing](../firmware/fc-inav/BATTERY_SENSE_CHECK.md).
