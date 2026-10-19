#pragma once

/* Pure state mapping, shared by the firmware and host checks. */
#include <math.h>
#include "fc_mavlink_probe.h"
#include "kogane_msg.h"

#define FC_HEARTBEAT_MAX_AGE_US 3000000LL
#define FC_ATTITUDE_MAX_AGE_US  1000000LL
#define FC_BATTERY_MAX_AGE_US   3000000LL

typedef struct {
    uint32_t heartbeats, attitudes, statuses;
    int64_t heartbeat_us, attitude_us, battery_us;
    bool armed;
    float yaw;
    uint16_t voltage_mv;
} fc_telemetry_sample_t;

static inline void fc_sample_update(fc_telemetry_sample_t *s,
                                    const fc_mavlink_probe_t *p, int64_t now_us)
{
    if (s->heartbeats != p->heartbeats) {
        s->heartbeats = p->heartbeats;
        s->heartbeat_us = now_us;
        s->armed = p->armed;
    }
    if (s->attitudes != p->attitudes) {
        s->attitudes = p->attitudes;
        s->attitude_us = now_us;
        s->yaw = p->yaw;
    }
    if (s->statuses != p->statuses) {
        s->statuses = p->statuses;
        s->battery_us = now_us;
        s->voltage_mv = p->voltage_mv;
    }
}

static inline bool fc_sample_fresh(uint32_t count, int64_t then_us,
                                    int64_t now_us, int64_t max_age_us)
{
    return count != 0 && now_us >= then_us && now_us - then_us <= max_age_us;
}

/* Returns FC fields only. Unknown/expired fields are zero with validity clear.
 * Position is unavailable; this path never marks it valid. */
static inline kgn_drone_state_t fc_sample_state(const fc_telemetry_sample_t *s,
                                                int64_t now_us)
{
    kgn_drone_state_t out = {0};
    if (!fc_sample_fresh(s->heartbeats, s->heartbeat_us, now_us,
                         FC_HEARTBEAT_MAX_AGE_US)) return out;
    out.flags = KGN_DS_F_FC_LINK_UP;
    if (s->armed) out.flags |= KGN_DS_F_ARMED;
    if (fc_sample_fresh(s->attitudes, s->attitude_us, now_us,
                         FC_ATTITUDE_MAX_AGE_US) && isfinite(s->yaw) &&
        s->yaw >= -3.141593f && s->yaw <= 3.141593f) {
        out.yaw_cd = (int16_t)lroundf(s->yaw * 5729.5779513f);
        out.flags |= KGN_DS_F_YAW_VALID;
    }
    if (fc_sample_fresh(s->statuses, s->battery_us, now_us,
                         FC_BATTERY_MAX_AGE_US) && s->voltage_mv != 0 &&
        s->voltage_mv != UINT16_MAX) {
        out.batt_mv = s->voltage_mv;
        out.flags |= KGN_DS_F_BATT_VALID;
    }
    return out;
}
