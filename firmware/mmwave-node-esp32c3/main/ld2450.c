/*
 * HLK-LD2450 report-frame parser.
 * Frame layout (30 bytes): AA FF 03 00 | 3 x [x_lo x_hi y_lo y_hi v_lo v_hi res_lo res_hi] | 55 CC
 * Coordinates/speed are little-endian; bit15 is the sign flag (1 = positive).
 */
#include <string.h>
#include "ld2450.h"

#define FRAME_LEN 30
static const uint8_t HEADER[4] = {0xAA, 0xFF, 0x03, 0x00};
static const uint8_t FOOTER[2] = {0x55, 0xCC};

static uint8_t  s_buf[FRAME_LEN];
static uint8_t  s_pos = 0;

/* LD2450 sign convention: bit15 set => positive magnitude in lower 15 bits. */
static int16_t decode_signed(uint16_t raw)
{
    // TODO(kogane): confirm against your module's firmware; some report -0x8000 offset.
    int16_t mag = (int16_t)(raw & 0x7FFF);
    return (raw & 0x8000) ? mag : (int16_t)(-mag);
}

static void decode_frame(ld2450_report_t *out)
{
    memset(out, 0, sizeof(*out));
    for (int i = 0; i < LD2450_MAX_TARGETS; ++i) {
        const uint8_t *t = &s_buf[4 + i * 8];
        uint16_t rx = t[0] | (t[1] << 8);
        uint16_t ry = t[2] | (t[3] << 8);
        uint16_t rv = t[4] | (t[5] << 8);
        uint16_t rr = t[6] | (t[7] << 8);
        ld2450_target_t *tg = &out->targets[i];
        tg->x_mm      = decode_signed(rx);
        tg->y_mm      = decode_signed(ry);
        tg->speed_cms = decode_signed(rv);
        tg->res_mm    = rr;
        tg->valid     = !(rx == 0 && ry == 0 && rv == 0);
        if (tg->valid) out->count++;
    }
}

bool ld2450_feed(const uint8_t *bytes, size_t n, ld2450_report_t *out)
{
    bool got = false;
    for (size_t i = 0; i < n; ++i) {
        uint8_t b = bytes[i];
        // Resync on header bytes.
        if (s_pos < 4) {
            if (b == HEADER[s_pos]) s_buf[s_pos++] = b;
            else s_pos = (b == HEADER[0]) ? (s_buf[0] = b, 1) : 0;
            continue;
        }
        s_buf[s_pos++] = b;
        if (s_pos == FRAME_LEN) {
            if (s_buf[28] == FOOTER[0] && s_buf[29] == FOOTER[1]) {
                decode_frame(out);
                got = true;
            }
            s_pos = 0;
        }
    }
    return got;
}
