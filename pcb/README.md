# PCB notes

The flight-controller source is in [FC/](FC/). The physical prototypes include hand repairs that are absent from these files.

## Fixes for the next revision

| Issue | Fix |
| --- | --- |
| R22 pulls ESP32 IO0 down and SW3 drives it high. | Add a 10 kΩ pull-up and a BOOT button to GND. The original circuit required SW3 for normal boot. The working prototype was repaired. |
| ESP32 EN floats and is connected to STM32 PB4. | Add a dedicated pull-up and reset timing. Design any STM32 reset control explicitly. |
| ESP32 native USB is not routed. | Route GPIO19/20 to a connector with ESD protection. |
| U11 speaker amplifier has SD_MODE tied to GND. | Correct the enable and channel-selection circuit. Do not connect the grounded pin directly to 3.3 V. |
| Battery ADC PC0 is unconnected. | Add a scaled, filtered divider and an accessible test point. |
| F1 is specified for 16 V and Q2 can exceed its ±8 V VGS rating. | Review the power path for full 4S/LiHV voltage, transients and USB backfeeding. |
| Connectors do not match some purchased modules. | Choose exact mating parts, label pin 1 and add strain relief and repair access. |
| LCD and camera reset share the STM32 reset net. LCD MISO is absent. | Add independent peripheral reset and route readback if required. |
| Some labels and firmware assumptions are stale. | Reconcile I2S directions, UARTs, the 25 MHz clock and motor timer/DMA assignments. Reserve the N16R8 memory pins. |

## Before ordering

- Reconcile BOM values and supplier IDs with the chosen components.
- Regenerate ERC and DRC. The saved report is historical.
- Verify the complete ESC harness pinout and every connector's orientation.
- Add test points for supply rails, reset, boot, UART and ADC signals.
- Check power selection and intended loads on the assembled revision.

Details are in the [firmware guide](../firmware/README.md), [pin map](../firmware/companion-esp32s3/PINMAP.md), [power review](../firmware/fc-inav/POWER_REVIEW.md) and [battery-sensing notes](../firmware/fc-inav/BATTERY_SENSE_CHECK.md).
