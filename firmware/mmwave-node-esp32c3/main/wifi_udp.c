/* Minimal Wi-Fi STA + UDP tx for the mmWave node (send-only). */
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "wifi_udp.h"

static const char *TAG = "wifi_udp";
static int s_sock = -1;
static struct sockaddr_in s_base;

int wifi_udp_send(const uint8_t *frame, size_t len)
{
    if (s_sock < 0) return -1;
    return sendto(s_sock, frame, len, 0, (struct sockaddr *)&s_base, sizeof(s_base));
}

static void on_evt(void *a, esp_event_base_t base, int32_t id, void *d)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) esp_wifi_connect();
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        s_base.sin_family = AF_INET;
        s_base.sin_port = htons(CONFIG_KGN_UDP_PORT);
        s_base.sin_addr.s_addr = inet_addr(CONFIG_KGN_BASE_IP);
        ESP_LOGI(TAG, "UDP ready -> %s:%d", CONFIG_KGN_BASE_IP, CONFIG_KGN_UDP_PORT);
    }
}

void wifi_udp_start(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_evt, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_evt, NULL, NULL);
    wifi_config_t wc = { 0 };
    strlcpy((char *)wc.sta.ssid, CONFIG_KGN_WIFI_SSID, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, CONFIG_KGN_WIFI_PASS, sizeof(wc.sta.password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
}
