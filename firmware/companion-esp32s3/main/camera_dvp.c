/*
 * OV2640 DVP camera skeleton -> MJPEG HTTP stream at http://<drone-ip>/stream.
 * Kept off the UDP control path so video never blocks setpoints (PROTOCOL.md §3).
 *
 * Enable espressif/esp32-camera in main/idf_component.yml, then flesh this out.
 */
#include "esp_log.h"
#include "camera_dvp.h"

static const char *TAG = "camera_dvp";

void camera_dvp_start(void)
{
    // TODO(kogane): esp_camera_init() with OV2640 pin map + PSRAM frame buffers,
    //               then start an httpd MJPEG stream handler.
    ESP_LOGI(TAG, "camera disabled (stub) — enable esp32-camera component to build");
}
