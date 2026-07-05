/* HLK-LD2450 report-frame parser. */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define LD2450_MAX_TARGETS 3

typedef struct {
    int16_t  x_mm;
    int16_t  y_mm;
    int16_t  speed_cms;
    uint16_t res_mm;
    bool     valid;
} ld2450_target_t;

typedef struct {
    ld2450_target_t targets[LD2450_MAX_TARGETS];
    uint8_t         count;
} ld2450_report_t;

/*
 * Feed received bytes; when a complete frame is decoded returns true and fills `out`.
 * Maintains internal framing state across calls, so pass bytes as they arrive.
 */
bool ld2450_feed(const uint8_t *bytes, size_t n, ld2450_report_t *out);
