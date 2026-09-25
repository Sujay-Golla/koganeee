#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* SPI display: ILI9341 320x240 panel. Touch (XPT2046) is not implemented yet. */
void display_spi_start(void);

/*
 * Hand a SCREEN_FRAME (0x30) payload to the display task. Copies the payload and
 * returns immediately — safe to call from the kgn_udp task. Returns false when the
 * chunk was dropped (display not up, malformed, queue full).
 * Payload layout: firmware/shared/PROTOCOL.md §1, `screen_frame`.
 */
bool display_submit_screen_frame(const uint8_t *payload, uint16_t len);
