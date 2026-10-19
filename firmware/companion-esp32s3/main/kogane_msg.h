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

/* src_id values. The drone companion is 0 (PROTOCOL.md §1: "drone=0"). */
#define KGN_SRC_ID_DRONE 0u

/* Roles for the heartbeat payload. */
typedef enum { KGN_ROLE_BASE = 0, KGN_ROLE_DRONE = 1, KGN_ROLE_NODE = 2 } kgn_role_t;

/*
 * drone_state.flags — per-field validity bitmask.
 *
 * This is NOT the header `flags` byte (that one carries ack_requested); it is the
 * payload byte at offset 10 of drone_state. Its purpose is to let the drone send
 * a well-formed 12-byte frame without claiming it measured things it cannot.
 *
 * A consumer MUST treat a field whose valid bit is clear as "no data" and ignore
 * the bytes, which will be zero. Sending zeros with the bit clear is not a
 * measurement of zero.
 *
 * This bridge exports fresh FC heartbeat/armed, yaw and voltage data. Position
 * remains invalid. LINK_Q is Wi-Fi RSSI, independent of FC reception.
 */
#define KGN_DS_F_POS_VALID    (1u << 0)  /* x_cm, y_cm, z_cm are real */
#define KGN_DS_F_YAW_VALID    (1u << 1)  /* yaw_cd is real */
#define KGN_DS_F_BATT_VALID   (1u << 2)  /* batt_mv is real */
#define KGN_DS_F_LINKQ_VALID  (1u << 3)  /* link_q is real */
#define KGN_DS_F_FC_LINK_UP   (1u << 4)  /* companion is talking to the STM32 */
#define KGN_DS_F_ARMED        (1u << 5)  /* FC reports armed (needs FC link) */
/* bits 6..7 reserved, must be 0 */

/*
 * drone_state.link_q — 0..100, derived from Wi-Fi RSSI by
 * kgn_rssi_to_link_q(). 0 also means "unknown" when KGN_DS_F_LINKQ_VALID
 * is clear, so always check the bit before reading it.
 */
#define KGN_RSSI_FLOOR_DBM  (-95)
#define KGN_RSSI_CEIL_DBM   (-35)

static inline uint8_t kgn_rssi_to_link_q(int rssi_dbm)
{
    if (rssi_dbm <= KGN_RSSI_FLOOR_DBM) return 1;   /* associated but awful; 0 is reserved */
    if (rssi_dbm >= KGN_RSSI_CEIL_DBM)  return 100;
    return (uint8_t)(((rssi_dbm - KGN_RSSI_FLOOR_DBM) * 100) /
                     (KGN_RSSI_CEIL_DBM - KGN_RSSI_FLOOR_DBM));
}

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
    uint8_t  flags;      // KGN_DS_F_* validity bitmask
    uint8_t  link_q;     // 0..100, only meaningful with KGN_DS_F_LINKQ_VALID
} kgn_drone_state_t;

typedef struct {
    uint32_t uptime_ms;
    uint8_t  role;       // kgn_role_t
} kgn_heartbeat_t;

/*
 * SCREEN_FRAME (0x30) chunk sub-header — see firmware/shared/PROTOCOL.md §1.
 * Every 0x30 payload starts with these 8 bytes, then a format-specific body.
 */
typedef struct {
    uint8_t fmt;         // kgn_screen_fmt_t
    uint8_t frame_id;    // rolling; groups the chunks of one logical frame
    uint8_t chunk_idx;   // 0-based index within the frame
    uint8_t chunk_cnt;   // total chunks, or 0 when the sender is streaming
    uint8_t flags;       // KGN_SF_F_*
    uint8_t reserved[3]; // must be 0
} kgn_screen_hdr_t;

/* fmt = KGN_SF_FMT_RGB565: tile header, then w*h RGB565 LE pixels row-major. */
typedef struct {
    uint16_t x, y, w, h;
} kgn_screen_tile_t;

/* fmt = KGN_SF_FMT_TEXT: line header, then the ASCII bytes (NOT NUL-terminated). */
typedef struct {
    uint8_t  row;        // text row index, 0..KGN_SF_TEXT_ROWS-1
    uint8_t  scale;      // glyph scale 1..4 over a 6x8 base cell
    uint16_t fg, bg;     // RGB565
} kgn_screen_text_t;

/*
 * AUDIO_TTS (0x40, base -> drone) and AUDIO_MIC (0x41, drone -> base) share this
 * 4-byte sub-header — see firmware/shared/PROTOCOL.md §1. Deliberately
 * symmetric: the two directions are the same codec, the same rate and the same
 * framing, so there is one layout to get right instead of two.
 *
 * `seq` here is the chunk index within an audio stream, which is NOT the header
 * seq (that one is a per-datagram rolling counter across all msg types). It
 * exists so a receiver can see a gap; neither side reorders or retransmits.
 *
 * Note the 4-byte size is chosen so the PCM body starts 2-byte aligned inside
 * the payload, which lets both ends treat it as an int16_t array directly.
 */
typedef struct {
    uint8_t  fmt;        // kgn_audio_fmt_t
    uint8_t  flags;      // KGN_AU_F_*
    uint16_t seq;        // rolling chunk index within this audio stream
} kgn_audio_hdr_t;
#pragma pack(pop)

typedef enum {
    KGN_SF_FMT_RGB565 = 1,
    KGN_SF_FMT_TEXT   = 2,
} kgn_screen_fmt_t;

#define KGN_SF_F_FIRST  (1u << 0)  /* clear the panel before applying this chunk */
#define KGN_SF_F_LAST   (1u << 1)  /* last chunk of the frame; commit / stop status overlay */
#define KGN_SF_F_STATUS (1u << 2)  /* hand the panel back to the local status screen */

/* Text mode grid: 10 rows of 24 px on a 240 px-high panel. */
#define KGN_SF_TEXT_ROWS   10
#define KGN_SF_TEXT_ROW_PX 24
#define KGN_SF_TEXT_MAX    53      /* 320 px / 6 px cell at scale 1 */

/*
 * Audio formats carried by AUDIO_TTS (0x40) / AUDIO_MIC (0x41).
 *
 * There is exactly one audio codec on this link and it is raw PCM. Opus is NOT
 * implemented: PROTOCOL.md used to say "PCM/opus chunk", which meant a receiver
 * could not know what it was being handed. `fmt` now says, per chunk.
 */
typedef enum {
    KGN_AUDIO_FMT_PCM_S16LE = 1,  /* body is int16 LE mono PCM @ KGN_AUDIO_FMT1_RATE_HZ */
    KGN_AUDIO_FMT_CTRL      = 2,  /* body is u8 cmd (kgn_audio_cmd_t), no PCM */
} kgn_audio_fmt_t;

/*
 * fmt 1 is a fixed-rate format: 16000 Hz, mono, 16-bit signed little-endian.
 * The rate is part of the format, not negotiated — a receiver that sees fmt 1
 * may assume 16 kHz without inspecting anything else. If the companion's
 * CONFIG_KGN_AUDIO_SAMPLE_RATE is moved off 16000 then fmt 1 no longer describes
 * what is on the wire, and audio_i2s.c says so loudly at boot.
 */
#define KGN_AUDIO_FMT1_RATE_HZ 16000

#define KGN_AU_F_START (1u << 0)  /* first chunk of an utterance/stream: flush any backlog first */
#define KGN_AU_F_END   (1u << 1)  /* last chunk of an utterance/stream */
/* bits 2..7 reserved, must be 0 */

/* fmt = KGN_AUDIO_FMT_CTRL: one command byte, base -> drone only. */
typedef enum {
    KGN_AUDIO_CMD_MIC_ON   = 1,  /* start streaming AUDIO_MIC to the base */
    KGN_AUDIO_CMD_MIC_OFF  = 2,  /* stop streaming AUDIO_MIC (the default state) */
    KGN_AUDIO_CMD_SELFTEST = 3,  /* play the local speaker self-test tone sequence */
    KGN_AUDIO_CMD_FLUSH    = 4,  /* drop queued TTS audio and go silent now */
} kgn_audio_cmd_t;

/*
 * Largest PCM body that fits one datagram:
 *   1500 MTU - 28 IP/UDP - 14 KGN header - 2 crc - 4 audio sub-header = 1452,
 * rounded down to a whole number of 16-sample groups for tidiness. 1440 bytes is
 * 720 samples, i.e. 45 ms at 16 kHz.
 */
#define KGN_AUDIO_PCM_MAX_BYTES 1440

/* Wire-size guards. These sizes are fixed by firmware/shared/PROTOCOL.md §1;
 * a packing regression must fail the build, not the link at runtime. */
_Static_assert(sizeof(kgn_header_t) == 14,
               "kgn_header_t must be 14 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_setpoint_t) == 9,
               "kgn_setpoint_t must be 9 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_drone_state_t) == 12,
               "kgn_drone_state_t must be 12 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_heartbeat_t) == 5,
               "kgn_heartbeat_t must be 5 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_screen_hdr_t) == 8,
               "kgn_screen_hdr_t must be 8 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_screen_tile_t) == 8,
               "kgn_screen_tile_t must be 8 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_screen_text_t) == 6,
               "kgn_screen_text_t must be 6 bytes (see firmware/shared/PROTOCOL.md §1)");
_Static_assert(sizeof(kgn_audio_hdr_t) == 4,
               "kgn_audio_hdr_t must be 4 bytes (see firmware/shared/PROTOCOL.md §1)");

/* CRC-16/CCITT-FALSE over the whole frame except the trailing crc field. */
uint16_t kgn_crc16(const uint8_t *data, size_t len);

/* Build a framed datagram into out (>= sizeof(header)+payload_len+2). Returns total bytes. */
size_t kgn_pack(uint8_t *out, uint8_t msg_type, uint16_t seq, uint32_t src_id,
                const void *payload, uint16_t payload_len);
