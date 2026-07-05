/*
 * KOGANE companion (ESP32-S3) — app entry.
 * Brings up Wi-Fi, then starts the payload + link tasks. Each task lives in its
 * own module and is a skeleton; see the corresponding .c file.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_log.h"

#include "wifi_udp.h"
#include "link_fc.h"
#include "audio_i2s.h"
#include "display_spi.h"
#include "camera_dvp.h"
#include "servo_ledc.h"

static const char *TAG = "kogane";

void app_main(void)
{
    ESP_LOGI(TAG, "Kogane companion boot");

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    // Networking first: the control + telemetry loops depend on UDP being up.
    wifi_udp_start();

    // FC bridge: MAVLink telemetry in, MSP override out (UART1).
    link_fc_start();

    // Payload subsystems (safe to start even if hardware not attached — they stub out).
    servo_ledc_start();
    audio_i2s_start();
    display_spi_start();
    camera_dvp_start();

    ESP_LOGI(TAG, "all subsystems started");
    // app_main returns; FreeRTOS keeps the created tasks running.
}
