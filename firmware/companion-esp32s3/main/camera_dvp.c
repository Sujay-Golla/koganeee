/*
 * OV2640 DVP camera -> MJPEG over HTTP at http://<drone-ip>/stream.
 * Kept off the UDP control path so video never blocks setpoints (PROTOCOL.md §3).
 *
 * Peripheral note: on the ESP32-S3 the DVP capture path is the LCD_CAM
 * peripheral driving GDMA, NOT I2S — that is only true of the original ESP32.
 * So this does not contend with the full-duplex I2S channel pair in
 * audio_i2s.c, and the two run at the same time. XCLK likewise comes out of
 * LCD_CAM's own clock divider on this target, not from LEDC, so it does not
 * touch the LEDC timer servo_ledc.c owns either. The `ledc_*` fields below are
 * set anyway, and set away from the servo's timer 0 / channel 0, so that a
 * build for a target where the driver *does* use LEDC for XCLK cannot quietly
 * reprogram the servo's 50 Hz timer.
 *
 * Frame format choice, and why VGA:
 *   The consumer is the base station's CV pipeline, which opens this URL with
 *   cv2.VideoCapture (base-station/kogane_base/vision/sources.py). That wants a
 *   steady frame rate far more than it wants pixels — a stalled capture reads as
 *   a frozen tracker. VGA 640x480 at JPEG quality 12 is ~25-45 KB a frame, so
 *   the 15 fps cap is ~4 Mbit/s, which shares a 2.4 GHz radio with setpoints and
 *   two directions of 16 kHz audio without trouble. It also leaves enough face
 *   pixels at a few metres for recognition to have something to work with, which
 *   QVGA does not. SVGA and up are available in menuconfig but were not chosen:
 *   the sensor can produce them, the link cannot keep them smooth.
 *   The OV2640 does the JPEG compression itself, so quality costs bytes on the
 *   wire, not CPU here — the ESP32 only moves the bitstream.
 *
 * Fail-soft contract, same as every other subsystem: if the module is absent or
 * miswired, esp_camera_init() fails, we log the error ONCE, and everything else
 * (Wi-Fi, UDP, telemetry, display, servo, audio) carries on untouched. The HTTP
 * server still comes up in that case and says so on / — a browser is the fastest
 * way to tell "camera broken" from "firmware broken" at the bench.
 *
 * SECURITY: this server is unauthenticated. Anyone who can reach the drone's IP
 * can watch the camera and there is no login, no token and no TLS. See the note
 * above httpd_start() below.
 */
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_http_server.h"
#include "esp_camera.h"

#include "camera_dvp.h"
#include "wifi_udp.h"

static const char *TAG = "camera_dvp";

/* Kconfig frame size choice -> driver enum. Kept here rather than in Kconfig so
 * the enum name and the pixel count stay next to each other. */
#if CONFIG_KGN_CAM_FRAMESIZE_QVGA
#define KGN_CAM_FRAMESIZE   FRAMESIZE_QVGA      /* 320x240 */
#define KGN_CAM_FRAMESIZE_S "QVGA 320x240"
#elif CONFIG_KGN_CAM_FRAMESIZE_HVGA
#define KGN_CAM_FRAMESIZE   FRAMESIZE_HVGA      /* 480x320 */
#define KGN_CAM_FRAMESIZE_S "HVGA 480x320"
#elif CONFIG_KGN_CAM_FRAMESIZE_SVGA
#define KGN_CAM_FRAMESIZE   FRAMESIZE_SVGA      /* 800x600 */
#define KGN_CAM_FRAMESIZE_S "SVGA 800x600"
#else
#define KGN_CAM_FRAMESIZE   FRAMESIZE_VGA       /* 640x480 */
#define KGN_CAM_FRAMESIZE_S "VGA 640x480"
#endif

/* ---- state ----
 * Written once at boot by camera_dvp_start(), read by the httpd task. */
static bool s_cam_ok;
static esp_err_t s_cam_err = ESP_OK;      /* why init failed, for / and /stream */
static httpd_handle_t s_httpd;

/* Counters, for the index page and the odd log line. Only the httpd task touches
 * these (there is exactly one httpd task), so no locking. */
static uint32_t s_frames_sent;
static uint32_t s_grab_fails;
static uint32_t s_not_jpeg;
static bool     s_streaming;              /* one stream at a time, see below */

/* ---- MJPEG framing ----
 * multipart/x-mixed-replace is what PROTOCOL.md §3 documents and what OpenCV's
 * FFmpeg backend expects. Content-Length per part is not optional in practice:
 * without it some clients buffer until the next boundary and the stream lags a
 * whole frame behind. */
#define KGN_MJPEG_BOUNDARY "kgnframe"
static const char *STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" KGN_MJPEG_BOUNDARY;
static const char *STREAM_BOUNDARY = "\r\n--" KGN_MJPEG_BOUNDARY "\r\n";
static const char *STREAM_PART_FMT = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static uint32_t now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

/* ---- handlers ---- */

/*
 * GET /stream — MJPEG, runs until the client goes away.
 *
 * This occupies the httpd task for the whole life of the stream (esp_http_server
 * is single-task), so / and /snapshot are unreachable while a stream is open.
 * That is a deliberate trade: a second httpd task would double the bulk-traffic
 * producer, and the endpoint that matters during a demo is this one.
 *
 * Only one stream is allowed at a time for the same reason — two viewers are two
 * copies of the same video on one radio.
 */
static esp_err_t stream_handler(httpd_req_t *req)
{
    if (!s_cam_ok) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "text/plain");
        return httpd_resp_sendstr(req, "camera not initialised\n");
    }
    if (s_streaming) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "text/plain");
        return httpd_resp_sendstr(req, "a stream is already open\n");
    }

    esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;
    /* The base station may well be on a different origin when someone wires the
     * stream into a page; this costs one header and saves an afternoon. */
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    s_streaming = true;
    ESP_LOGI(TAG, "stream opened");

#if CONFIG_KGN_CAM_STREAM_MAX_FPS > 0
    const uint32_t min_period_ms = 1000 / CONFIG_KGN_CAM_STREAM_MAX_FPS;
    uint32_t next_due_ms = now_ms();
#endif
    char part[64];
    uint32_t opened_ms = now_ms();
    uint32_t frames = 0;

    while (1) {
#if CONFIG_KGN_CAM_STREAM_MAX_FPS > 0
        /* Rate cap before the grab, not after the send: sleeping here also stops
         * the capture path from filling buffers we are only going to drop. */
        uint32_t t = now_ms();
        if ((int32_t)(next_due_ms - t) > 0) vTaskDelay(pdMS_TO_TICKS(next_due_ms - t));
        next_due_ms = now_ms() + min_period_ms;
#endif
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) {
            /* Transient on a marginal ribbon: count it, give the control path the
             * CPU back, and try again rather than tearing the stream down. */
            s_grab_fails++;
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        if (fb->format != PIXFORMAT_JPEG) {
            /* Cannot happen with pixel_format = PIXFORMAT_JPEG, but converting in
             * software here would cost more CPU than the control path can spare,
             * so it is counted and dropped rather than handled. */
            s_not_jpeg++;
            esp_camera_fb_return(fb);
            continue;
        }

        int hdr_len = snprintf(part, sizeof(part), STREAM_PART_FMT, (unsigned)fb->len);
        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res == ESP_OK) res = httpd_resp_send_chunk(req, part, hdr_len);
        if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
        esp_camera_fb_return(fb);       /* return before reacting to res: never leak a fb */
        if (res != ESP_OK) break;       /* client closed the socket — the normal exit */

        s_frames_sent++;
        frames++;
    }

    s_streaming = false;
    uint32_t dur_ms = now_ms() - opened_ms;
    ESP_LOGI(TAG, "stream closed after %lu frames in %lu ms (%lu fps)",
             (unsigned long)frames, (unsigned long)dur_ms,
             (unsigned long)(dur_ms ? frames * 1000 / dur_ms : 0));
    /* Close the chunked response cleanly so httpd frees the socket now. */
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

/* GET /snapshot — one JPEG. The cheap "is the camera alive" check: it works from
 * a browser, from curl, and from cv2.imread over HTTP. */
static esp_err_t snapshot_handler(httpd_req_t *req)
{
    if (!s_cam_ok) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "text/plain");
        return httpd_resp_sendstr(req, "camera not initialised\n");
    }

    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        s_grab_fails++;
        httpd_resp_set_status(req, "500 Internal Server Error");
        httpd_resp_set_type(req, "text/plain");
        return httpd_resp_sendstr(req, "frame grab failed\n");
    }

    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=kogane.jpg");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (res == ESP_OK) s_frames_sent++;
    return res;
}

/* GET / — status and the two links. Deliberately plain: this page exists so the
 * camera is verifiable from a phone on the same Wi-Fi without any tooling. */
static esp_err_t index_handler(httpd_req_t *req)
{
    char ip[16];
    wifi_udp_get_ip_str(ip, sizeof(ip));

    char body[900];
    int n = snprintf(body, sizeof(body),
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>Kogane companion</title></head><body>"
        "<h1>Kogane companion</h1>"
        "<p>camera: <b>%s</b>%s%s</p>"
        "<p>frame size: %s &middot; jpeg quality: %d &middot; frame buffers: %d"
        " &middot; fps cap: %d</p>"
        "<p>ip: %s &middot; uptime: %lu s &middot; frames served: %lu"
        " &middot; grab fails: %lu</p>"
        "<p><a href=\"/stream\">/stream</a> (MJPEG) &middot; "
        "<a href=\"/snapshot\">/snapshot</a> (single JPEG)</p>"
        "<p><img src=\"/snapshot\" alt=\"no frame\" width=\"320\"></p>"
        "<p><small>unauthenticated — anyone on this network can watch"
        "</small></p></body></html>",
        s_cam_ok ? "up" : "down",
        s_cam_ok ? "" : " — ",
        s_cam_ok ? "" : esp_err_to_name(s_cam_err),
        KGN_CAM_FRAMESIZE_S, CONFIG_KGN_CAM_JPEG_QUALITY, CONFIG_KGN_CAM_FB_COUNT,
        CONFIG_KGN_CAM_STREAM_MAX_FPS,
        ip, (unsigned long)(now_ms() / 1000),
        (unsigned long)s_frames_sent, (unsigned long)s_grab_fails);

    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, body, (n > 0 && n < (int)sizeof(body)) ? n : HTTPD_RESP_USE_STRLEN);
}

/* ---- bring-up ---- */

static void http_start(void)
{
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = CONFIG_KGN_CAM_HTTP_PORT;
    cfg.ctrl_port = CONFIG_KGN_CAM_HTTP_PORT + 1000;   /* keep off 32768 if the port moves */
    /*
     * Priority: bulk video must lose every race on this chip. kgn_udp is 6,
     * kgn_tlm and kgn_aout 5, kgn_servo and kgn_amic 4, kgn_disp 3 — so the
     * server runs at CONFIG_KGN_CAM_HTTP_PRIO (2 by default), under all of them.
     * A setpoint that arrives while a frame is being pushed out preempts the
     * push; the frame arrives a few milliseconds later and nobody notices.
     * The other way round, iNAV's MSP receiver times out after 200 ms and cuts
     * the motors, which everybody notices.
     */
    cfg.task_priority = CONFIG_KGN_CAM_HTTP_PRIO;
    cfg.stack_size = 4096;
    /* The MJPEG handler never returns while a client is attached, so a socket
     * that dies mid-stream has to be reclaimable or the server wedges. */
    cfg.lru_purge_enable = true;
    cfg.max_open_sockets = 4;
    cfg.max_uri_handlers = 4;

    /*
     * SECURITY — this is an open, unauthenticated HTTP server on the drone.
     * There is no password, no token and no TLS, and /stream is a live camera
     * feed of whatever the aircraft is pointed at. Anyone who can route to the
     * drone's address can watch it. That is the same posture as PROTOCOL.md §3
     * describes and it is fine on an isolated bench network; it is not fine on a
     * shared or public one. Auth is deliberately NOT bolted on here — HTTP Basic
     * over plaintext would add a login prompt and no actual secrecy, which is
     * worse than being honest about the exposure.
     */
    esp_err_t err = httpd_start(&s_httpd, &cfg);
    if (err != ESP_OK) {
        /* Fail soft: no stream is survivable. */
        ESP_LOGE(TAG, "httpd_start(port %d) failed (%s) — no camera stream",
                 CONFIG_KGN_CAM_HTTP_PORT, esp_err_to_name(err));
        s_httpd = NULL;
        return;
    }

    static const httpd_uri_t uri_index = {
        .uri = "/", .method = HTTP_GET, .handler = index_handler,
    };
    static const httpd_uri_t uri_stream = {
        .uri = "/stream", .method = HTTP_GET, .handler = stream_handler,
    };
    static const httpd_uri_t uri_snapshot = {
        .uri = "/snapshot", .method = HTTP_GET, .handler = snapshot_handler,
    };
    httpd_register_uri_handler(s_httpd, &uri_index);
    httpd_register_uri_handler(s_httpd, &uri_stream);
    httpd_register_uri_handler(s_httpd, &uri_snapshot);

    ESP_LOGI(TAG, "http up on port %d: / /stream /snapshot (UNAUTHENTICATED)",
             CONFIG_KGN_CAM_HTTP_PORT);
}

void camera_dvp_start(void)
{
    /* Every pin from Kconfig — the DVP bus was cross-checked against the PCB
     * netlist (U4 pad -> net map), see PINMAP.md. SCCB shares the board's only
     * I2C pair. pin_reset is -1 because the camera's RESET is on the board-wide
     * RESET net (SW1 / STM32 NRST), not on a GPIO: the sensor can only be
     * software-reset over SCCB, and a sensor too wedged to answer SCCB needs a
     * board reset or a power cycle.
     *
     * pin_pwdn IS real on this board: net PMDN, GPIO46, camera FPC1 pad 8. This
     * file is its only owner — display_spi.c used to drive it as a bogus "panel
     * reset" and park it HIGH, which held the sensor powered down. The driver is
     * left to manage the line rather than us toggling it: camera_probe() pulses
     * it HIGH 10 ms then LOW 10 ms before SCCB probing and leaves it LOW, which
     * is exactly the active-high power-up sequence the OV2640 wants, and doing
     * it ourselves would only risk racing the driver's own sequence. */
    camera_config_t cfg = {
        .pin_pwdn       = CONFIG_KGN_CAM_PWDN,
        .pin_reset      = CONFIG_KGN_CAM_RESET,
        .pin_xclk       = CONFIG_KGN_CAM_XCLK,
        .pin_sccb_sda   = CONFIG_KGN_I2C_SDA,
        .pin_sccb_scl   = CONFIG_KGN_I2C_SCL,
        .pin_d0         = CONFIG_KGN_CAM_D0,
        .pin_d1         = CONFIG_KGN_CAM_D1,
        .pin_d2         = CONFIG_KGN_CAM_D2,
        .pin_d3         = CONFIG_KGN_CAM_D3,
        .pin_d4         = CONFIG_KGN_CAM_D4,
        .pin_d5         = CONFIG_KGN_CAM_D5,
        .pin_d6         = CONFIG_KGN_CAM_D6,
        .pin_d7         = CONFIG_KGN_CAM_D7,
        .pin_vsync      = CONFIG_KGN_CAM_VSYNC,
        .pin_href       = CONFIG_KGN_CAM_HSYNC,
        .pin_pclk       = CONFIG_KGN_CAM_PCLK,

        .xclk_freq_hz   = CONFIG_KGN_CAM_XCLK_HZ,
        /* Inert on the ESP32-S3 (XCLK comes from LCD_CAM's own divider) but kept
         * off timer 0 / channel 0, which servo_ledc.c owns. */
        .ledc_timer     = LEDC_TIMER_1,
        .ledc_channel   = LEDC_CHANNEL_1,

        .pixel_format   = PIXFORMAT_JPEG,
        .frame_size     = KGN_CAM_FRAMESIZE,
        .jpeg_quality   = CONFIG_KGN_CAM_JPEG_QUALITY,
        .fb_count       = CONFIG_KGN_CAM_FB_COUNT,
        /* 8 MB octal PSRAM is confirmed working on this board, and JPEG frame
         * buffers have no business in the 512 KB of internal RAM that Wi-Fi and
         * lwIP are competing for. */
        .fb_location    = CAMERA_FB_IN_PSRAM,
        /* LATEST, not WHEN_EMPTY: a CV consumer wants the newest frame, and with
         * two buffers WHEN_EMPTY can hand out a frame that is one period stale. */
        .grab_mode      = CAMERA_GRAB_LATEST,
    };

    /* NOTE: D8/D9 (CONFIG_KGN_CAM_D8=1, _D9=2) are routed on the PCB but are not
     * passed to the driver. The OV2640 is configured for 8-bit output and the
     * esp32-camera DVP path only takes d0..d7; the top two data lines exist for a
     * 10-bit sensor this board does not have. Left wired and unused on purpose —
     * do not "fix" this by shuffling the bus. */

    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        /* Log ONCE and carry on. A missing or miswired module is the expected
         * bench state, not a boot failure: Wi-Fi, UDP, telemetry, display, servo
         * and audio are all untouched by this.
         * ESP_ERR_CAMERA_NOT_DETECTED (0x20001) means SCCB found no sensor —
         * no module, ribbon seated backwards, or CONFIG_KGN_CAM_PWDN set to -1
         * with the line floating high. */
        s_cam_err = err;
        ESP_LOGE(TAG, "esp_camera_init failed (%s) — camera disabled, rest of the "
                      "system unaffected", esp_err_to_name(err));
    } else {
        s_cam_ok = true;
        ESP_LOGI(TAG, "OV2640 up: %s q%d fb=%d xclk=%d Hz, pclk=%d xclk_io=%d "
                      "vsync=%d href=%d sda=%d scl=%d pwdn=%d reset=%d",
                 KGN_CAM_FRAMESIZE_S, CONFIG_KGN_CAM_JPEG_QUALITY,
                 CONFIG_KGN_CAM_FB_COUNT, CONFIG_KGN_CAM_XCLK_HZ,
                 CONFIG_KGN_CAM_PCLK, CONFIG_KGN_CAM_XCLK, CONFIG_KGN_CAM_VSYNC,
                 CONFIG_KGN_CAM_HSYNC, CONFIG_KGN_I2C_SDA, CONFIG_KGN_I2C_SCL,
                 CONFIG_KGN_CAM_PWDN, CONFIG_KGN_CAM_RESET);

        /* TODO(kogane): sensor orientation. Whether the FPC module ends up
         * mounted upright, inverted or on its side in the nose is a mechanical
         * question nobody has answered yet, so no set_vflip/set_hmirror here.
         * Fix it with the sensor_t handle once the module is physically in the
         * airframe — flipping in firmware is free, flipping every frame on the
         * base station is not. */
    }

    /* The server comes up either way. With the camera down, / reports the init
     * error and the two image endpoints return 503 — that turns "is the camera
     * broken or is the firmware broken" into one page load. */
    http_start();
}
