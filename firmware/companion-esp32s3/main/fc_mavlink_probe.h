#pragma once

/* Bounded MAVLink v1/v2 bench decoder. HEARTBEAT, SYS_STATUS, ATTITUDE and PARAM_VALUE
 * CRC extras are known here. Other IDs are skipped, not reported as verified.
 * Signed/incompatible v2 packets are unsupported. No data is sent to the FC
 * and publication uses a separate snapshot with per-message freshness. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    uint8_t frame[280];
    size_t used;
    uint32_t bytes, valid, bad_crc, skipped, heartbeats, attitudes, statuses, parameters;
    uint8_t sysid, compid;
    uint8_t heartbeat_sysid, heartbeat_compid, parameter_sysid, parameter_compid;
    bool armed;
    uint16_t voltage_mv;
    float roll, pitch, yaw;
} fc_mavlink_probe_t;

static inline uint16_t fc_probe_crc_byte(uint16_t crc, uint8_t value)
{
    uint8_t tmp = value ^ (uint8_t)crc;
    tmp ^= (uint8_t)(tmp << 4);
    return (crc >> 8) ^ ((uint16_t)tmp << 8) ^
           ((uint16_t)tmp << 3) ^ (tmp >> 4);
}

static inline void fc_probe_discard(fc_mavlink_probe_t *p, size_t count)
{
    p->used -= count;
    memmove(p->frame, p->frame + count, p->used);
}

static inline void fc_probe_byte(fc_mavlink_probe_t *p, uint8_t byte)
{
    p->bytes++;
    if (p->used == sizeof(p->frame)) fc_probe_discard(p, 1);
    p->frame[p->used++] = byte;
    for (;;) {
        if (!p->used) return;
        uint8_t *f = p->frame;
        if (f[0] != 0xfe && f[0] != 0xfd) {
            fc_probe_discard(p, 1);
            continue;
        }
        if (p->used < 2) return;
        bool v2 = f[0] == 0xfd;
        size_t header = v2 ? 10 : 6;
        if (p->used < header) return;
        size_t len = f[1];
        size_t total = header + len + 2 + ((v2 && (f[2] & 1)) ? 13 : 0);
        if (p->used < total) return;
        uint32_t id = v2 ? (uint32_t)f[7] | ((uint32_t)f[8] << 8) |
                                   ((uint32_t)f[9] << 16) : f[5];
        uint8_t extra;
        size_t max_len;
        switch (id) {
        case 0:  extra = 50;  max_len = 9;  break;
        case 1:  extra = 124; max_len = 43; break;
        case 22: extra = 220; max_len = 25; break;
        case 30: extra = 39;  max_len = 28; break;
        default:
            p->skipped++;
            fc_probe_discard(p, total);
            continue;
        }
        if ((v2 && f[2] != 0) || len == 0 || len > max_len ||
            (!v2 && len != (id == 1 ? 31 : max_len))) {
            p->skipped++;
            fc_probe_discard(p, total);
            continue;
        }
        uint16_t crc = 0xffff;
        for (size_t i = 1; i < header + len; ++i)
            crc = fc_probe_crc_byte(crc, f[i]);
        crc = fc_probe_crc_byte(crc, extra);
        uint16_t expected = f[header + len] | ((uint16_t)f[header + len + 1] << 8);
        if (crc != expected) {
            p->bad_crc++;
            fc_probe_discard(p, 1);
            continue;
        }
        p->valid++;
        p->sysid = f[v2 ? 5 : 3];
        p->compid = f[v2 ? 6 : 4];
        uint8_t payload[43] = {0};
        memcpy(payload, f + header, len); /* v2 omitted trailing bytes are zero */
        if (id == 0) {
            p->heartbeats++;
            p->heartbeat_sysid = p->sysid;
            p->heartbeat_compid = p->compid;
            p->armed = (payload[6] & 128) != 0;
        } else if (id == 22) {
            p->parameters++;
            p->parameter_sysid = p->sysid;
            p->parameter_compid = p->compid;
        } else if (id == 1) {
            p->statuses++;
            p->voltage_mv = payload[14] | ((uint16_t)payload[15] << 8);
        } else if (id == 30) {
            p->attitudes++;
            memcpy(&p->roll, payload + 4, sizeof(float));
            memcpy(&p->pitch, payload + 8, sizeof(float));
            memcpy(&p->yaw, payload + 12, sizeof(float));
        }
        fc_probe_discard(p, total);
    }
}
