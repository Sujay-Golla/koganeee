/*
 * KOGANE KGN UDP datagram — C mirror of firmware/shared/PROTOCOL.md §1.
 * Keep in sync with base-station/kogane_base/protocol.py.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

#define KGN_MAGIC0 'K'
#define KGN_MAGIC1 'G'
#define KGN_MAGIC2 'N'
#define KGN_VERSION 1

typedef enum {
    KGN_MMWAVE_TARGETS = 0x01,
    KGN_SETPOINT       = 0x10,
    KGN_MODE_CMD       = 0x11,
    KGN_DRONE_STATE    = 0x20,
    KGN_SCREEN_FRAME   = 0x30,
    KGN_AUDIO_TTS      = 0x40,
    KGN_AUDIO_MIC      = 0x41,
    KGN_HEARTBEAT      = 0x7F,
} kgn_msg_type_t;

typedef enum { KGN_CTRL_HOLD = 0, KGN_CTRL_VELOCITY = 1, KGN_CTRL_POSITION = 2 } kgn_ctrl_mode_t;
typedef enum { KGN_MODE_IDLE=0, KGN_MODE_ARM=1, KGN_MODE_TAKEOFF=2, KGN_MODE_FOLLOW=3,
               KGN_MODE_LAND=4, KGN_MODE_DOCK=5, KGN_MODE_FAILSAFE=6 } kgn_mode_t;

#pragma pack(push, 1)
typedef struct {
    uint8_t  magic[3];   // "KGN"
    uint8_t  version;    // KGN_VERSION
    uint8_t  msg_type;   // kgn_msg_type_t
    uint8_t  flags;      // bit0 = ack_requested
    uint16_t seq;
    uint32_t src_id;
    uint16_t len;        // payload length
    // payload[len] follows, then uint16_t crc16
} kgn_header_t;

typedef struct {
    int16_t vx_cms, vy_cms, vz_cms;
    int16_t yaw_rate_cds;
    uint8_t ctrl_mode;   // kgn_ctrl_mode_t
} kgn_setpoint_t;

typedef struct {
    int16_t  x_cm, y_cm, z_cm;
    int16_t  yaw_cd;
    uint16_t batt_mv;
    uint8_t  flags;
    uint8_t  link_q;
} kgn_drone_state_t;
#pragma pack(pop)

/* CRC-16/CCITT-FALSE over the whole frame except the trailing crc field. */
uint16_t kgn_crc16(const uint8_t *data, size_t len);

/* Build a framed datagram into out (>= sizeof(header)+payload_len+2). Returns total bytes. */
size_t kgn_pack(uint8_t *out, uint8_t msg_type, uint16_t seq, uint32_t src_id,
                const void *payload, uint16_t payload_len);
