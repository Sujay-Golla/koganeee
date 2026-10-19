# STM32 flight controller

The custom STM32F722 board runs iNAV 9.1.0. It uses a 25 MHz crystal, an ICM45686 IMU, custom motor outputs and ELRS on UART3. Configurator 9.1.1 was used for setup.

## Flash the tested image

Use [inav_9.1.0_MATEKF722_uart3-pb10-pb11.hex](inav_9.1.0_MATEKF722_uart3-pb10-pb11.hex). This image was flashed and verified on the prototype. A stock online MATEKF722 image does not match the board.

SHA-256:

```text
68fe6438b728f1db63ab9dedb0c02c29d640017b75ecaf2494fcf0c1aa365f69
```

1. Remove propellers, disconnect the battery and save the current `diff all` output.
2. Connect STM32 USB. Hold SW2/BOOT while resetting with SW1 or connecting USB to enter DFU.
3. Open Firmware Flasher, select DFU and enable **No reboot sequence**.
4. Choose **Load Firmware [Local]** and select the HEX above. Leave full erase off for an update of the same custom target and version. A fresh configuration requires complete setup afterward.
5. Flash, reset without BOOT and reconnect to the serial port.
6. Check `resource` and `status`. Confirm the mappings below and healthy gyro/accelerometer readings.

Do not paste [config/kogane-fc.diff](config/kogane-fc.diff) as a restore script. It records design intentions and is not a verified configuration backup.

## Board mapping

| Function | Assignment |
| --- | --- |
| Motor 1 | PA0, TIM2 CH1. |
| Motor 2 | PA1, TIM2 CH2. |
| Motor 3 | PA2, TIM2 CH3. |
| Motor 4 | PA3, TIM5 CH4 with the tested DMA option. |
| ELRS UART3 | PB10 TX and PB11 RX. |
| Companion UART1 | PA9 TX and PA10 RX. |
| IMU | ICM45686 on SPI1 with PA4 chip select. |
| ToF | VL53L1X on I2C1. |
| Battery ADC | PC0 is unconnected in the saved PCB. |

The version string can stay unchanged after a custom build. Verify UART3 on B10/B11 to distinguish the patched pin layout from the stock target.

## Configure and test

- Enable UART3 Serial RX. Select SERIAL and CRSF in Receiver, with inversion and half-duplex off.
- Use DSHOT300 and enable `PWM_OUTPUT_ENABLE`. Verify each motor output with propellers removed.
- Set the mixer and board alignment to the actual aircraft geometry. The current build uses Quad + with its nose toward M4.
- Calibrate the accelerometer and check that the Status model follows physical roll and pitch.
- Assign ARM and ANGLE switches. Test disarming and radio-loss failsafe before flight. The tested failsafe procedure is DROP.
- For companion telemetry, dedicate UART1 to MAVLink at 115200. Keep MSP off on that UART and retain USB MSP access.
- To enable ToF, set `rangefinder_hardware = VL53L1X`, save and verify changing distance readings. This alone does not enable altitude hold.

See [flight checks](../Demo/FIRST_FLIGHT_PLAN.md) and [FC link checks](../companion-esp32s3/FC_LINK_CHECK.md).

## Hardware limits

The battery ADC has no verified divider. Its reported voltage and cell count are invalid. See [battery sensing](BATTERY_SENSE_CHECK.md) for the proposed repair and [power review](POWER_REVIEW.md) for F1 and Q2 rating concerns.

The physical boards have different repairs. Check the [PCB notes](../../pcb/README.md) before assuming the saved design matches a particular board.

## Rebuilding from source

The included patches record changes made to a customized MATEKF722 checkout.

| File | Change |
| --- | --- |
| [MATEKF722.CMakeLists.txt](patches/MATEKF722.CMakeLists.txt) | Selects the 25 MHz HSE. |
| [system_stm32f7xx-pllm.patch](patches/system_stm32f7xx-pllm.patch) | Derives PLL_M from HSE_VALUE. |
| [MATEKF722-motors-pa0-pa3.patch](patches/MATEKF722-motors-pa0-pa3.patch) | Maps the motor timers and avoids the TIM2 DMA conflict. |
| [MATEKF722-uart3-pb10-pb11.patch](patches/MATEKF722-uart3-pb10-pb11.patch) | Moves UART3 to the PCB's receiver pins. |

These files are not a complete replacement target for a clean upstream checkout. The target also needs the correct IMU configuration and USB settings. Stock PB12 VBUS sensing does not match this PCB. The [KOGANEF722 target](target/KOGANEF722/) remains an unfinished skeleton.

Use an iNAV 9.1.0 source tree with the board changes reconciled. After installing the upstream build dependencies, build MATEKF722 in WSL or Linux.

```bash
git clone https://github.com/iNavFlight/inav.git
cd inav
git checkout 9.1.0
# Apply and verify the board-specific changes before building.
mkdir -p build
cd build
cmake ..
make -j$(nproc) MATEKF722
```

Changing only `HSE_MHZ` is insufficient. PLL_M must also use the actual crystal frequency. A board that disappears from USB after flashing a stock image can still enter ROM DFU for recovery.
