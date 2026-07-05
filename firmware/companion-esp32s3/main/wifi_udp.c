/*
 * Wi-Fi (STA) + Kogane UDP link.
 * Receives SETPOINT / MODE_CMD / SCREEN / TTS from the base and dispatches them;
 * sends DRONE_STATE / mic audio back. Datagram format: shared/PROTOCOL.md §1.
 */
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"

#include "wifi_udp.h"
#include "kogane_msg.h"
#include "link_fc.h"

static const char *TAG = "wifi_udp";
static int s_sock = -1;
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
    if (s_sock < 0) return -1;
    return sendto(s_sock, frame, len, 0,
                  (struct sockaddr *)&s_base_addr, sizeof(s_base_addr));
}

/* ---- inbound datagram handling ---- */
static void handle_datagram(const uint8_t *buf, int n)
{
    if (n < (int)sizeof(kgn_header_t) + 2) return;
    const kgn_header_t *h = (const kgn_header_t *)buf;
    if (h->magic[0] != 'K' || h->magic[1] != 'G' || h->magic[2] != 'N') return;
    if (h->version != KGN_VERSION) { ESP_LOGW(TAG, "version mismatch"); return; }
    const uint8_t *payload = buf + sizeof(kgn_header_t);

    switch (h->msg_type) {
    case KGN_SETPOINT:
        // Off-board velocity/position command -> forward to FC as MSP override.
        link_fc_apply_setpoint((const kgn_setpoint_t *)payload);
        break;
    case KGN_MODE_CMD:
        // TODO(kogane): arm/takeoff/land/dock/failsafe handling.
        break;
    case KGN_SCREEN_FRAME:
        // TODO(kogane): push chunk to display_spi.
        break;
    case KGN_AUDIO_TTS:
        // TODO(kogane): push PCM chunk to audio_i2s speaker ring.
        break;
    default:
        break;
    }
}

static void udp_task(void *arg)
{
    uint8_t rx[1500];
    while (1) {
        struct sockaddr_in from; socklen_t fl = sizeof(from);
        int n = recvfrom(s_sock, rx, sizeof(rx), 0, (struct sockaddr *)&from, &fl);
        if (n > 0) handle_datagram(rx, n);
    }
}

/* ---- Wi-Fi bring-up ---- */
static void on_wifi_evt(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) esp_wifi_connect();
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGI(TAG, "got IP, opening UDP socket");
        s_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        struct sockaddr_in local = { .sin_family = AF_INET,
            .sin_addr.s_addr = htonl(INADDR_ANY), .sin_port = htons(CONFIG_KGN_UDP_PORT) };
        bind(s_sock, (struct sockaddr *)&local, sizeof(local));
        s_base_addr.sin_family = AF_INET;
        s_base_addr.sin_port = htons(CONFIG_KGN_UDP_PORT);
        s_base_addr.sin_addr.s_addr = inet_addr(CONFIG_KGN_BASE_IP);
        xTaskCreate(udp_task, "kgn_udp", 4096, NULL, 6, NULL);
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
    ESP_LOGI(TAG, "wifi starting, ssid=%s", CONFIG_KGN_WIFI_SSID);
}
