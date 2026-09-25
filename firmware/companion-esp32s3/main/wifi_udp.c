/*
 * Wi-Fi (STA) + Kogane UDP link.
 * Receives SETPOINT / MODE_CMD / SCREEN / TTS from the base and dispatches them;
 * sends DRONE_STATE / mic audio back. Datagram format: shared/PROTOCOL.md §1.
 */
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "wifi_udp.h"
#include "kogane_msg.h"
#include "link_fc.h"
#include "audio_i2s.h"
#include "display_spi.h"
#include "servo_ledc.h"
#include "telemetry.h"

static const char *TAG = "wifi_udp";
/* Written by the event task, read by udp_task and any sender: volatile so the
 * fd is actually re-read rather than cached across the loop. */
static volatile int s_sock = -1;
static struct sockaddr_in s_base_addr;

/* ---- protocol helpers (declared in kogane_msg.h) ---- */
uint16_t kgn_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; ++b)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

size_t kgn_pack(uint8_t *out, uint8_t msg_type, uint16_t seq, uint32_t src_id,
                const void *payload, uint16_t payload_len)
{
    kgn_header_t h = {
        .magic = {KGN_MAGIC0, KGN_MAGIC1, KGN_MAGIC2},
        .version = KGN_VERSION, .msg_type = msg_type, .flags = 0,
        .seq = seq, .src_id = src_id, .len = payload_len,
    };
    memcpy(out, &h, sizeof(h));
    if (payload_len && payload) memcpy(out + sizeof(h), payload, payload_len);
    uint16_t crc = kgn_crc16(out, sizeof(h) + payload_len);
    memcpy(out + sizeof(h) + payload_len, &crc, sizeof(crc));
    return sizeof(h) + payload_len + sizeof(crc);
}

int wifi_udp_send(const uint8_t *frame, size_t len)
{
    int sock = s_sock;                 /* sample once: don't test one value and use another */
    if (sock < 0) return -1;
    return sendto(sock, frame, len, 0,
                  (struct sockaddr *)&s_base_addr, sizeof(s_base_addr));
}

/* ---- link status ---- */

/* Cached at GOT_IP rather than queried, so readers never touch esp_netif from a
 * random task. Sized for a dotted quad plus NUL. */
static char s_ip_str[16];

bool wifi_udp_get_ip_str(char *out, size_t n)
{
    if (!out || !n) return false;
    if (s_ip_str[0] == '\0') { strlcpy(out, "0.0.0.0", n); return false; }
    strlcpy(out, s_ip_str, n);
    return true;
}

bool wifi_udp_get_rssi(int *rssi_dbm)
{
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return false;
    if (rssi_dbm) *rssi_dbm = ap.rssi;
    return true;
}

/* ---- inbound datagram handling ---- */

/* Rejected datagrams are counted, not logged per-packet: a corrupt or hostile
 * sender must not be able to flood the console off the control path. */
#define KGN_RX_REJECT_LOG_PERIOD_MS 5000

typedef enum {
    KGN_REJ_VERSION = 0,
    KGN_REJ_SHORT,      /* fewer bytes on the wire than header+len+crc */
    KGN_REJ_CRC,
    KGN_REJ_PAYLOAD_LEN,/* h->len != expected size for msg_type */
    KGN_REJ_RANGE,      /* well-framed but the value is outside the enum */
    KGN_REJ_COUNT,
} kgn_reject_t;

static uint32_t s_rej[KGN_REJ_COUNT];
static uint32_t s_rej_last_log_ms;

static void kgn_reject(kgn_reject_t why)
{
    s_rej[why]++;
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    if (s_rej_last_log_ms == 0) { s_rej_last_log_ms = now; return; }
    if ((uint32_t)(now - s_rej_last_log_ms) < KGN_RX_REJECT_LOG_PERIOD_MS) return;
    s_rej_last_log_ms = now;
    ESP_LOGW(TAG, "rx rejects: ver=%lu short=%lu crc=%lu len=%lu range=%lu",
             (unsigned long)s_rej[KGN_REJ_VERSION], (unsigned long)s_rej[KGN_REJ_SHORT],
             (unsigned long)s_rej[KGN_REJ_CRC], (unsigned long)s_rej[KGN_REJ_PAYLOAD_LEN],
             (unsigned long)s_rej[KGN_REJ_RANGE]);
}

/* Expected payload size per msg_type, or -1 when variable/unconstrained. */
static int kgn_expected_payload_len(uint8_t msg_type)
{
    switch (msg_type) {
    case KGN_SETPOINT: return (int)sizeof(kgn_setpoint_t);
    case KGN_MODE_CMD: return 1;
    default:           return -1;
    }
}

/*
 * MODE_CMD (0x11) dispatch.
 *
 * Mode -> screen mechanism mapping. The retractable screen is a body panel: it
 * must be stowed whenever the airframe is, or about to be, flying, and out only
 * when the drone is stationary and facing a person.
 *
 *   IDLE     -> retract   powered but parked; nothing should be sticking out
 *   ARM       -> retract  motors live, treat as flight
 *   TAKEOFF   -> retract  in flight
 *   FOLLOW    -> DEPLOY   the headline case: drone is tracking a person and the
 *                         screen is the thing they look at
 *   LAND      -> retract  in flight
 *   DOCK      -> DEPLOY   docked and stationary, interaction mode
 *   FAILSAFE  -> retract  get the mechanism out of the way, unconditionally
 *
 * Everything past the servo is still unimplemented, deliberately: arming,
 * takeoff, landing and docking all need the FC link, which cannot receive on
 * this board (PINMAP.md). The mode is recorded and the screen responds; the
 * flight behaviour does not exist yet and is marked below rather than faked.
 *
 * Runs on the kgn_udp task, so it only records state and posts to the servo
 * queue — servo_screen_*() are non-blocking and rate limited internally.
 */
static void handle_mode_cmd(uint8_t mode)
{
    if (mode > KGN_MODE_FAILSAFE) { kgn_reject(KGN_REJ_RANGE); return; }

    uint8_t prev = telemetry_get_mode();
    telemetry_set_mode(mode);

    switch ((kgn_mode_t)mode) {
    case KGN_MODE_FOLLOW:
    case KGN_MODE_DOCK:
        servo_screen_deploy();
        break;
    case KGN_MODE_IDLE:
    case KGN_MODE_ARM:
    case KGN_MODE_TAKEOFF:
    case KGN_MODE_LAND:
    case KGN_MODE_FAILSAFE:
        servo_screen_retract();
        break;
    }

    /* TODO(kogane): flight-side mode handling — ARM/TAKEOFF/LAND need MSP arm +
     * NAV mode changes to iNAV, DOCK needs the precision-landing sequence, and
     * FAILSAFE needs to force the FC's own failsafe rather than just stop
     * sending. All of it is blocked on the PA10 -> IO3 rework (PINMAP.md); until
     * the FC link can receive, the companion has no way to confirm the FC acted,
     * and sending one-way arm commands it cannot verify is worse than refusing. */

    if (mode != prev)
        ESP_LOGI(TAG, "mode %u -> %u (screen %s)", prev, mode,
                 (mode == KGN_MODE_FOLLOW || mode == KGN_MODE_DOCK)
                     ? "deploy" : "retract");
}

static void handle_datagram(const uint8_t *buf, int n)
{
    if (n < (int)sizeof(kgn_header_t) + 2) return;
    const kgn_header_t *h = (const kgn_header_t *)buf;
    if (h->magic[0] != 'K' || h->magic[1] != 'G' || h->magic[2] != 'N') return;
    if (h->version != KGN_VERSION) { kgn_reject(KGN_REJ_VERSION); return; }

    /* Length before content: everything below indexes into the received bytes. */
    const size_t body_end = sizeof(kgn_header_t) + (size_t)h->len;
    if ((size_t)n < body_end + 2) { kgn_reject(KGN_REJ_SHORT); return; }

    uint16_t rx_crc;
    memcpy(&rx_crc, buf + body_end, sizeof(rx_crc));   /* LE on the wire and on target */
    if (rx_crc != kgn_crc16(buf, body_end)) { kgn_reject(KGN_REJ_CRC); return; }

    int want = kgn_expected_payload_len(h->msg_type);
    if (want >= 0 && (int)h->len != want) { kgn_reject(KGN_REJ_PAYLOAD_LEN); return; }

    const uint8_t *payload = buf + sizeof(kgn_header_t);

    switch (h->msg_type) {
    case KGN_SETPOINT: {
        // Off-board velocity/position command -> forward to FC as MSP override.
        // Copy out of the packed rx buffer: the cast would otherwise be unaligned.
        kgn_setpoint_t sp;
        memcpy(&sp, payload, sizeof(sp));
        link_fc_apply_setpoint(&sp);
        break;
    }
    case KGN_MODE_CMD:
        handle_mode_cmd(payload[0]);
        break;
    case KGN_SCREEN_FRAME:
        /* Copies and queues; never renders on this task. A drop here is counted
         * inside display_spi and logged there, rate limited. */
        display_submit_screen_frame(payload, h->len);
        break;
    case KGN_AUDIO_TTS:
        /* Copies and queues; never touches I2S on this task. Drops are counted
         * inside audio_i2s and logged there, rate limited. fmt 2 (CTRL) chunks
         * are handled inline there too — they only flip flags. */
        audio_submit_tts(payload, h->len);
        break;
    default:
        break;
    }
}

/* Idle wait when there is no socket to read from: the task outlives any single
 * association attempt, so it must park rather than spin on a -1 fd. */
#define KGN_UDP_NO_SOCK_DELAY_MS 200
#define KGN_UDP_RX_ERR_DELAY_MS  50

static void udp_task(void *arg)
{
    uint8_t rx[1500];
    while (1) {
        int sock = s_sock;
        if (sock < 0) {
            vTaskDelay(pdMS_TO_TICKS(KGN_UDP_NO_SOCK_DELAY_MS));
            continue;
        }
        struct sockaddr_in from; socklen_t fl = sizeof(from);
        int n = recvfrom(sock, rx, sizeof(rx), 0, (struct sockaddr *)&from, &fl);
        if (n > 0) handle_datagram(rx, n);
        else if (n < 0) vTaskDelay(pdMS_TO_TICKS(KGN_UDP_RX_ERR_DELAY_MS));
    }
}

/* ---- Wi-Fi bring-up ---- */

/* Bounded exponential backoff on reconnect. Retrying flat-out in the event
 * handler starves the Wi-Fi task and buries the disconnect reason in the log. */
#define KGN_WIFI_BACKOFF_MIN_MS 500
#define KGN_WIFI_BACKOFF_MAX_MS 12000

static uint32_t s_backoff_ms = KGN_WIFI_BACKOFF_MIN_MS;
static esp_timer_handle_t s_reconnect_timer;

static void wifi_reconnect_cb(void *arg)
{
    esp_wifi_connect();
}

static void wifi_schedule_reconnect(void)
{
    if (!s_reconnect_timer) {
        const esp_timer_create_args_t args = {
            .callback = wifi_reconnect_cb, .name = "kgn_wifi_retry",
        };
        if (esp_timer_create(&args, &s_reconnect_timer) != ESP_OK) {
            esp_wifi_connect();   /* degrade to immediate retry rather than stall */
            return;
        }
    }
    esp_timer_stop(s_reconnect_timer);   /* no-op if not running */
    esp_timer_start_once(s_reconnect_timer, (uint64_t)s_backoff_ms * 1000);

    uint32_t next = s_backoff_ms * 2;
    s_backoff_ms = (next > KGN_WIFI_BACKOFF_MAX_MS) ? KGN_WIFI_BACKOFF_MAX_MS : next;
}

/* IP_EVENT_STA_GOT_IP fires on *every* association, not just the first, so the
 * UDP bring-up below has to be idempotent.
 *
 * Socket lifetime choice: the socket is created once and kept open for the rest
 * of the boot. It is bound to INADDR_ANY:port, not to the address the DHCP lease
 * handed us, so it stays valid across reassociation and there is nothing to
 * rebind. Keeping it means s_sock is never replaced while udp_task might be
 * blocked in recvfrom() on the old fd -- the close-and-reopen alternative has no
 * safe point to close from here, since the event task cannot know the rx task
 * has left the old descriptor. Consequence: s_sock only ever moves -1 -> valid,
 * so no fd is leaked and no reader sees a closed or swapped fd.
 */
static bool s_udp_task_started;

static void udp_link_start_once(void)
{
    if (s_sock < 0) {
        int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock < 0) {
            ESP_LOGE(TAG, "socket() failed, errno=%d", errno);
        } else {
            struct sockaddr_in local = { .sin_family = AF_INET,
                .sin_addr.s_addr = htonl(INADDR_ANY), .sin_port = htons(CONFIG_KGN_UDP_PORT) };
            if (bind(sock, (struct sockaddr *)&local, sizeof(local)) < 0) {
                ESP_LOGE(TAG, "bind(port %d) failed, errno=%d", CONFIG_KGN_UDP_PORT, errno);
                close(sock);        /* don't publish a half-set-up fd */
            } else {
                s_sock = sock;      /* published only once bound */
            }
        }
        /* On failure s_sock stays -1: wifi_udp_send returns -1, udp_task parks,
         * and the next GOT_IP retries. */
    }

    if (!s_udp_task_started) {
        if (xTaskCreate(udp_task, "kgn_udp", 4096, NULL, 6, NULL) == pdPASS) {
            s_udp_task_started = true;
        } else {
            ESP_LOGE(TAG, "xTaskCreate(kgn_udp) failed");
        }
    }
}

static void on_wifi_evt(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        s_backoff_ms = KGN_WIFI_BACKOFF_MIN_MS;
        esp_wifi_connect();
    }
    else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *d = (const wifi_event_sta_disconnected_t *)data;
        /* reason 15 = 4WAY_HANDSHAKE_TIMEOUT / 205 = CONNECTION_FAIL -> usually a
         * wrong password; 201 = NO_AP_FOUND -> wrong or absent SSID. */
        ESP_LOGW(TAG, "disconnected, reason=%d, retry in %lu ms",
                 d ? d->reason : -1, (unsigned long)s_backoff_ms);
        s_ip_str[0] = '\0';   /* lease is gone: stop reporting a stale address */
        wifi_schedule_reconnect();
    }
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_backoff_ms = KGN_WIFI_BACKOFF_MIN_MS;
        const ip_event_got_ip_t *g = (const ip_event_got_ip_t *)data;
        if (g) snprintf(s_ip_str, sizeof(s_ip_str), IPSTR, IP2STR(&g->ip_info.ip));
        ESP_LOGI(TAG, "got IP %s, opening UDP socket", s_ip_str);
        s_base_addr.sin_family = AF_INET;
        s_base_addr.sin_port = htons(CONFIG_KGN_UDP_PORT);
        s_base_addr.sin_addr.s_addr = inet_addr(CONFIG_KGN_BASE_IP);
        udp_link_start_once();
    }
}

void wifi_udp_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_evt, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_wifi_evt, NULL, NULL);

    wifi_config_t wc = { 0 };
    strlcpy((char *)wc.sta.ssid, CONFIG_KGN_WIFI_SSID, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, CONFIG_KGN_WIFI_PASS, sizeof(wc.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Disable Wi-Fi modem power save. The driver default is WIFI_PS_MIN_MODEM,
     * which parks the radio between beacons and stalls inbound datagrams in
     * bursts — confirmed in the boot log ("wifi:pm start, type: 1") and measured
     * as real loss on the control path (5 datagrams sent, 3 received).
     *
     * Why that is not survivable here: the setpoints carried in those datagrams
     * become MSP RC overrides to iNAV, whose MSP receiver timeout is 200 ms with
     * failsafe_procedure = DROP. A power-save stall longer than 200 ms is
     * indistinguishable from RC link loss, and iNAV cuts the motors.
     *
     * Must be called after esp_wifi_start() so it applies to the running driver.
     * Tradeoff: the radio stays awake, so idle current draw goes up. Accepted —
     * a heavier battery budget beats an in-flight motor cut. */
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    ESP_LOGI(TAG, "wifi starting (power save disabled), ssid=%s", CONFIG_KGN_WIFI_SSID);
}
