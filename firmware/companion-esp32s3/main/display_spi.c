/*
 * SPI display skeleton: ILI9341 + XPT2046 touch.
 * Renders SCREEN_FRAME chunks streamed from the base (shared/PROTOCOL.md 0x30).
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "display_spi.h"

static const char *TAG = "display_spi";

static void display_task(void *arg)
{
    while (1) {
        // TODO(kogane): init ILI9341 over spi_master; blit queued SCREEN_FRAME chunks;
        //               poll XPT2046 touch and report events back to base.
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void display_spi_start(void)
{
    xTaskCreate(display_task, "display", 4096, NULL, 4, NULL);
    ESP_LOGI(TAG, "display task started (stub)");
}
