#pragma once
#include "kogane_msg.h"

/* Start the FC UART link task (MAVLink telemetry in, MSP override out). */
void link_fc_start(void);

/* Convert a base-station setpoint into an MSP RC override to the FC. */
void link_fc_apply_setpoint(const kgn_setpoint_t *sp);
