/*
 * KOGANE F722 — iNAV custom target (SKELETON)
 *
 * This is a starting-point board definition for the custom STM32F722RET6 FC.
 * Pins follow hardware/DESIGN.md §5. Macro names/APIs drift between iNAV majors,
 * so reconcile every TODO(kogane) against src/main/target/<a similar F722 target>
 * in the iNAV release you build (e.g. MATEKF722SE) before relying on this.
 */
#pragma once

#define TARGET_BOARD_IDENTIFIER "KGF7"
#define USBD_PRODUCT_STRING     "KoganeF722"

/* ---- MCU ---- */
#define USE_TARGET_CONFIG

/* ---- IMU: ICM-45686 on SPI1 ---- */
#define USE_IMU_ICM45686            // TODO(kogane): confirm the exact driver macro in your iNAV tree
#define IMU_ICM45686_ALIGN     CW0_DEG   // TODO(kogane): set per PCB orientation
#define ICM45686_CS_PIN        PA4
#define ICM45686_SPI_BUS       BUS_SPI1
#define GYRO_1_EXTI_PIN        PC4        // INT1
// #define GYRO_2_EXTI_PIN     PB0        // INT2 (optional)

#define USE_SPI
#define USE_SPI_DEVICE_1
#define SPI1_SCK_PIN           PA5
#define SPI1_MISO_PIN          PA6
#define SPI1_MOSI_PIN          PA7

/* ---- I2C1: VL53L1X (+ optional baro) ---- */
#define USE_I2C
#define USE_I2C_DEVICE_1
#define I2C1_SCL               PB6
#define I2C1_SDA               PB7
#define USE_RANGEFINDER
#define USE_RANGEFINDER_VL53L1X

/* ---- UARTs ---- */
#define USE_VCP
#define USE_UART1                          // ESP32 (MSP + MAVLink telem)
#define UART1_TX_PIN           PA9
#define UART1_RX_PIN           PA10
#define USE_UART3                          // ELRS/CRSF RX
#define UART3_TX_PIN           PB10
#define UART3_RX_PIN           PB11
#define USE_UART6                          // spare
#define UART6_TX_PIN           PC6
#define UART6_RX_PIN           PC7
#define SERIAL_PORT_COUNT      4            // VCP + UART1 + UART3 + UART6

/* ---- Motors: DShot on TIM2 ---- */
#define USE_DSHOT
#define USE_ESC_SENSOR
// Motor pins PA0..PA3 are declared in target.c timerHardware[].
// TODO(kogane): verify DShot DMA streams (DESIGN.md §5 — TIM2_CH4 -> DMA1_Stream7).

/* ---- SDMMC blackbox ---- */
#define USE_SDCARD
#define USE_SDCARD_SDIO
#define SDCARD_DETECT_PIN      PB3

/* ---- ADC ---- */
#define USE_ADC
#define ADC_CHANNEL_1_PIN      PC1          // TODO(kogane): reconcile PC0 vs PC1 with hardware
#define VBAT_ADC_CHANNEL       ADC_CHN_1

/* ---- LED ---- */
#define LED0_PIN               PB9

/* ---- clocks ---- */
#define USE_HSE
#define HSE_VALUE              25000000

/* ---- features enabled by default ---- */
#define DEFAULT_FEATURES       (FEATURE_VBAT | FEATURE_BLACKBOX)

/* ---- port usage masks (reconcile with iNAV version) ---- */
#define TARGET_IO_PORTA        0xffff
#define TARGET_IO_PORTB        0xffff
#define TARGET_IO_PORTC        0xffff
#define TARGET_IO_PORTD        (BIT(2))
#define TARGET_IO_PORTH        (BIT(0) | BIT(1))
