#pragma once
#include "kogane_msg.h"

/* Start FC telemetry; TX is input except during the optional bounded read query. */
void link_fc_start(void);

/* Discard setpoints in RX_ONLY mode. The legacy transmit path is unverified. */
void link_fc_apply_setpoint(const kgn_setpoint_t *sp);

/* Thread-safe fresh FC fields; unavailable fields have zero bytes/clear flags. */
kgn_drone_state_t link_fc_state(void);
