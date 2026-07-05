/*
 * KOGANE mmWave node (ESP32-C3): LD2450 UART -> parse -> KGN UDP to base.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "nvs_flash.h"
#include "esp_log.h"

#include "ld2450.h"
#include "wifi_udp.h"

static const char *TAG = "node";
#define LD_UART  (CONFIG_KGN_LD2450_UART_NUM)

/* --- KGN framing (mirror of shared/PROTOCOL.md; send-only subset) --- */
static uint16_t crc16(const uint8_t *d, size_t n)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < n; ++i) {
        crc ^= (uint16_t)d[i] << 8;
        for (int b = 0; b < 8; ++b) crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

static uint16_t s_seq = 0;

static void send_targets(const ld2450_report_t *r)
{
    uint8_t frame[64];
    // header (14 bytes)
    frame[0]='K'; frame[1]='G'; frame[2]='N'; frame[3]=1; frame[4]=0x01; frame[5]=0;
    frame[6]=s_seq & 0xFF; frame[7]=s_seq >> 8; s_seq++;
    uint32_t src = CONFIG_KGN_NODE_ID;
    memcpy(&frame[8], &src, 4);
    // payload: u8 count + count * 8 bytes
    uint8_t *p = &frame[14];
    uint8_t count = 0, *pcount = p++; // reserve count byte
    for (int i = 0; i < LD2450_MAX_TARGETS; ++i) {
        if (!r->targets[i].valid) continue;
        int16_t x = r->targets[i].x_mm, y = r->targets[i].y_mm, v = r->targets[i].speed_cms;
        uint16_t res = r->targets[i].res_mm;
        memcpy(p, &x, 2); memcpy(p+2, &y, 2); memcpy(p+4, &v, 2); memcpy(p+6, &res, 2);
        p += 8; count++;
    }
    *pcount = count;
    uint16_t plen = 1 + count * 8;
    frame[12] = plen & 0xFF; frame[13] = plen >> 8;
    uint16_t crc = crc16(frame, 14 + plen);
    memcpy(&frame[14 + plen], &crc, 2);
    wifi_udp_send(frame, 14 + plen + 2);
}

static void node_task(void *arg)
{
    uint8_t rx[128];
    ld2450_report_t report;
    while (1) {
        int n = uart_read_bytes(LD_UART, rx, sizeof(rx), pdMS_TO_TICKS(50));
        if (n > 0 && ld2450_feed(rx, n, &report)) {
            send_targets(&report);
        }
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    wifi_udp_start();

    uart_config_t uc = {
        .baud_rate = 256000, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(LD_UART, 1024, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(LD_UART, &uc));
    ESP_ERROR_CHECK(uart_set_pin(LD_UART, CONFIG_KGN_LD2450_TX, CONFIG_KGN_LD2450_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    xTaskCreate(node_task, "ld2450", 4096, NULL, 6, NULL);
    ESP_LOGI(TAG, "node %d up", CONFIG_KGN_NODE_ID);
}
