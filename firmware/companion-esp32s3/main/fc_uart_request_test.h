#pragma once

/* Only this fixed read request can be encoded here. No settings or RC payload. */
#include "fc_mavlink_probe.h"

static inline size_t fc_request_frame(uint8_t out[10], uint8_t seq,
                                      uint8_t target_system, uint8_t target_component)
{
    const uint8_t frame[8] = {0xfe, 2, seq, 255, 190, 21,
                              target_system, target_component};
    memcpy(out, frame, sizeof(frame));
    uint16_t crc = 0xffff;
    for (size_t i = 1; i < sizeof(frame); ++i) crc = fc_probe_crc_byte(crc, out[i]);
    crc = fc_probe_crc_byte(crc, 159); /* PARAM_REQUEST_LIST CRC extra */
    out[8] = (uint8_t)crc;
    out[9] = (uint8_t)(crc >> 8);
    return 10;
}

typedef enum { FC_REQUEST_IDLE, FC_REQUEST_SEND, FC_REQUEST_PASS, FC_REQUEST_FAIL }
    fc_request_action_t;

typedef struct {
    int64_t start_us, deadline_us;
    uint32_t baseline_replies;
    uint8_t attempts, target_system, target_component;
    bool done;
} fc_request_test_t;

static inline fc_request_action_t fc_request_tick(fc_request_test_t *t,
        const fc_mavlink_probe_t *p, bool fresh_disarmed_fc, int64_t now_us)
{
    if (t->done) return FC_REQUEST_IDLE;
    if (!t->attempts) {
        if (!fresh_disarmed_fc) {
            if (now_us - t->start_us >= 15000000) {
                t->done = true;
                return FC_REQUEST_FAIL;
            }
            return FC_REQUEST_IDLE;
        }
        t->target_system = p->heartbeat_sysid;
        t->target_component = p->heartbeat_compid;
    } else {
        if (p->parameters != t->baseline_replies &&
            p->parameter_sysid == t->target_system &&
            p->parameter_compid == t->target_component) {
            t->done = true;
            return FC_REQUEST_PASS;
        }
        if (!fresh_disarmed_fc) {
            t->done = true;
            return FC_REQUEST_FAIL;
        }
        if (now_us < t->deadline_us) return FC_REQUEST_IDLE;
        if (t->attempts == 3) {
            t->done = true;
            return FC_REQUEST_FAIL;
        }
    }
    t->attempts++;
    t->baseline_replies = p->parameters;
    t->deadline_us = now_us + 2000000;
    return FC_REQUEST_SEND;
}
