/*
 * I2S audio skeleton.
 *   Mic:     INMP441 (I2S RX)  -> chunk -> wifi_udp_send(AUDIO_MIC) to base.
 *   Speaker: MAX98357A (I2S TX) <- AUDIO_TTS chunks queued from wifi_udp.
 * Two I2S peripherals (or one duplex) — pins set per DESIGN.md §7 / menuconfig.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "audio_i2s.h"

static const char *TAG = "audio_i2s";

static void audio_task(void *arg)
{
    while (1) {
        // TODO(kogane): i2s_channel_read() mic frames, VAD/gain, send AUDIO_MIC.
        // TODO(kogane): drain TTS ring, i2s_channel_write() to speaker.
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void audio_i2s_start(void)
{
    // TODO(kogane): configure I2S std mode for mic + speaker (new_i2s_channel API).
    xTaskCreate(audio_task, "audio", 4096, NULL, 5, NULL);
    ESP_LOGI(TAG, "audio task started (stub)");
}
