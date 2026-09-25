#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "kogane_msg.h"

/* Start the outbound telemetry task (DRONE_STATE + HEARTBEAT to the base). */
void telemetry_start(void);

/*
 * Last mode requested by the base over MODE_CMD (0x11). Defaults to
 * KGN_MODE_IDLE until the first valid command arrives. Kept here rather than in
 * wifi_udp.c so the display can read it without reaching into the rx path.
 */
void    telemetry_set_mode(uint8_t mode);
uint8_t telemetry_get_mode(void);

/* Human-readable name for a kgn_mode_t, for logs and the status screen. */
const char *telemetry_mode_name(uint8_t mode);

/* Frames actually handed to the socket since boot, for the status screen. */
uint32_t telemetry_tx_count(void);
