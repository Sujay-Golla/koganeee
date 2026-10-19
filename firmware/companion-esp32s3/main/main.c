/*
 * KOGANE companion (ESP32-S3) — app entry.
 * Staged bring-up: each subsystem has a default-off Kconfig switch so the
 * repaired board can be checked one peripheral at a time.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_log.h"

#include "wifi_udp.h"
#include "telemetry.h"
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

    // Keep the first flash to boot + NVS only. Enable one stage at a time.
#if defined(CONFIG_KGN_BRINGUP_WIFI)
    wifi_udp_start();
#endif

#if defined(CONFIG_KGN_BRINGUP_FC_LINK)
    link_fc_start();
#endif

    // Servo precedes display because the status page reads servo state.
#if defined(CONFIG_KGN_BRINGUP_SERVO)
    servo_ledc_start();
#endif
#if defined(CONFIG_KGN_BRINGUP_AUDIO)
    audio_i2s_start();
#endif
#if defined(CONFIG_KGN_BRINGUP_DISPLAY)
    display_spi_start();
#endif
#if defined(CONFIG_KGN_BRINGUP_CAMERA)
    camera_dvp_start();
#endif

#if defined(CONFIG_KGN_BRINGUP_TELEMETRY)
    telemetry_start();
#endif

    ESP_LOGI(TAG, "selected bring-up subsystems started");
    // app_main returns; FreeRTOS keeps the created tasks running.
}
