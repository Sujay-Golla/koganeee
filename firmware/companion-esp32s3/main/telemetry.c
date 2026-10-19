/*
 * Outbound telemetry: DRONE_STATE (0x20) + HEARTBEAT (0x7F) to the base station.
 *
 * Why this exists at all: before it, the drone was receive-only. The base station
 * learns the drone's source address from inbound datagrams, so a periodic send is
 * what makes the link bidirectional and observable from the laptop side.
 *
 * Honesty rule for this module: every field in drone_state is either measured or
 * flagged invalid in the `flags` bitmask (KGN_DS_F_*, defined in kogane_msg.h).
 * Fresh CRC-checked FC heartbeat, yaw and battery fields come from link_fc.c.
 * Missing/expired fields stay invalid. Position is not provided by this path.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "telemetry.h"
#include "wifi_udp.h"
#include "kogane_msg.h"
#include "link_fc.h"

static const char *TAG = "telemetry";

/* Largest frame this module emits: header + drone_state + crc. */
#define TLM_FRAME_MAX (sizeof(kgn_header_t) + sizeof(kgn_drone_state_t) + 2)

/* The tick the task runs at. DRONE_STATE and HEARTBEAT are both derived from it
 * by counting ticks, so there is one timebase and no drift between the two. */
#define TLM_TICK_MS 20

static uint16_t s_seq;              /* rolling, shared across both msg types */
static uint32_t s_tx_frames;
static volatile uint8_t s_mode = KGN_MODE_IDLE;

void telemetry_set_mode(uint8_t mode) { s_mode = mode; }
uint8_t telemetry_get_mode(void)      { return s_mode; }
uint32_t telemetry_tx_count(void)     { return s_tx_frames; }

const char *telemetry_mode_name(uint8_t mode)
{
    switch (mode) {
    case KGN_MODE_IDLE:     return "IDLE";
    case KGN_MODE_ARM:      return "ARM";
    case KGN_MODE_TAKEOFF:  return "TAKEOFF";
    case KGN_MODE_FOLLOW:   return "FOLLOW";
    case KGN_MODE_LAND:     return "LAND";
    case KGN_MODE_DOCK:     return "DOCK";
    case KGN_MODE_FAILSAFE: return "FAILSAFE";
    default:                return "?";
    }
}

static void tlm_send(uint8_t msg_type, const void *payload, uint16_t len)
{
    uint8_t frame[TLM_FRAME_MAX];
    size_t n = kgn_pack(frame, msg_type, s_seq++, KGN_SRC_ID_DRONE, payload, len);
    if (wifi_udp_send(frame, n) > 0) s_tx_frames++;
    /* A failed send is not logged per-frame: with no socket yet this fires at the
     * telemetry rate and would bury the association log. The status screen and
     * telemetry_tx_count() are how you notice nothing is going out. */
}

static void send_drone_state(void)
{
    kgn_drone_state_t st = link_fc_state();

    int rssi;
    if (wifi_udp_get_rssi(&rssi)) {
        st.link_q = kgn_rssi_to_link_q(rssi);
        st.flags |= KGN_DS_F_LINKQ_VALID;
    }

    tlm_send(KGN_DRONE_STATE, &st, sizeof(st));
}

static void send_heartbeat(void)
{
    kgn_heartbeat_t hb = {
        .uptime_ms = (uint32_t)(esp_timer_get_time() / 1000),
        .role = KGN_ROLE_DRONE,
    };
    tlm_send(KGN_HEARTBEAT, &hb, sizeof(hb));
}

static void telemetry_task(void *arg)
{
    /* Round to whole ticks. At 20 ms/tick this is exact for 1/2/5/10/25/50 Hz. */
    const uint32_t state_period = (1000 / CONFIG_KGN_TELEM_STATE_HZ) / TLM_TICK_MS;
    const uint32_t hb_period    = (1000 / CONFIG_KGN_TELEM_HEARTBEAT_HZ) / TLM_TICK_MS;
    uint32_t tick = 0;

    ESP_LOGI(TAG, "telemetry task: DRONE_STATE %d Hz, HEARTBEAT %d Hz -> %s:%d",
             CONFIG_KGN_TELEM_STATE_HZ, CONFIG_KGN_TELEM_HEARTBEAT_HZ,
             CONFIG_KGN_BASE_IP, CONFIG_KGN_UDP_PORT);

    TickType_t last = xTaskGetTickCount();
    while (1) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(TLM_TICK_MS));
        tick++;
        if (state_period && (tick % state_period) == 0) send_drone_state();
        if (hb_period    && (tick % hb_period)    == 0) send_heartbeat();
    }
}

void telemetry_start(void)
{
    /* Priority 5: below kgn_udp (6) so inbound control always wins the CPU, but
     * above the cosmetic display (3) and the servo sweep (4) so a busy panel
     * cannot stall the only signal the base has that the drone is alive. */
    if (xTaskCreate(telemetry_task, "kgn_tlm", 3072, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "xTaskCreate(kgn_tlm) failed — drone will stay silent");
    }
}
