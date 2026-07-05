/*
 * KOGANE F722 — iNAV custom target (SKELETON)
 *
 * timerHardware[] maps the DShot motor pins and any timer-driven IO.
 * The exact struct fields (DEF_TIM signature, DMA opts) depend on your iNAV
 * release — copy the pattern from a nearby F722 target's target.c and adjust pins.
 */
#include <stdint.h>
#include "platform.h"
#include "drivers/io.h"
#include "drivers/timer.h"
#include "drivers/bus.h"

timerHardware_t timerHardware[] = {
    // TODO(kogane): use the DEF_TIM(...) macro form from your iNAV version.
    // Motors on TIM2 CH1..CH4 (PA0..PA3), DShot-capable, unique DMA per channel.
    // DEF_TIM(TIM2, CH1, PA0, TIM_USE_MOTOR, 0, 0),  // M1
    // DEF_TIM(TIM2, CH2, PA1, TIM_USE_MOTOR, 0, 0),  // M2
    // DEF_TIM(TIM2, CH3, PA2, TIM_USE_MOTOR, 0, 0),  // M3
    // DEF_TIM(TIM2, CH4, PA3, TIM_USE_MOTOR, 0, 1),  // M4 -> alt DMA stream (see DESIGN.md §5)
};
const int timerHardwareCount = sizeof(timerHardware) / sizeof(timerHardware[0]);

// SPI/I2C/UART/SDIO device tables are declared here too in most iNAV targets.
// TODO(kogane): add busDevice_t / spiPinConfig entries per your iNAV version.
