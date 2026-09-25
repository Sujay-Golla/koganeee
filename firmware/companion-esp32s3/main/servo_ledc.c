/*
 * MG90S screen-rollout servo (LEDC 50 Hz PWM) on CONFIG_KGN_SERVO_GPIO (GPIO42,
 * net SRV_SIG — see PINMAP.md). This drives the retractable screen mechanism.
 *
 * Two layers:
 *   - servo_set_deg()  : immediate duty write, clamped. No task needed.
 *   - servo_sweep_to() : queues an interpolated move onto the kgn_servo task so
 *                        the mechanism travels deliberately instead of snapping.
 *                        Safe to call from the UDP rx task; it only posts.
 *
 * MODE_CMD drives this via wifi_udp.c; the mode -> position mapping is documented
 * there, next to the dispatch.
 */
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "servo_ledc.h"

static const char *TAG = "servo_ledc";

#define SERVO_TIMER     LEDC_TIMER_0
#define SERVO_MODE      LEDC_LOW_SPEED_MODE
#define SERVO_CHANNEL   LEDC_CHANNEL_0
#define SERVO_RES_BITS  14
#define SERVO_RES       LEDC_TIMER_14_BIT
#define SERVO_FREQ_HZ   50                  // 20 ms period
#define SERVO_PERIOD_US 20000
#define SERVO_MIN_US    500                 // ~0 deg   (MG90S spec, tune to mechanism)
#define SERVO_MAX_US    2400                // ~180 deg (MG90S spec, tune to mechanism)

/*
 * Timer resolution / frequency math, checked rather than assumed:
 *
 *   LEDC low-speed mode on the ESP32-S3 sources from APB (80 MHz) under
 *   LEDC_AUTO_CLK. The peripheral needs freq_hz * 2^bits <= clk, i.e.
 *       50 Hz * 2^14 = 819200 Hz  <=  80 MHz            -> OK
 *   The headroom is large: the resolution ceiling at 50 Hz is
 *       floor(log2(80e6 / 50)) = floor(log2(1.6e6)) = 20 bits.
 *   14 bits is therefore comfortably inside the hardware limit, and the
 *   pre-divider (80e6 / 819200 = 97.66) lands well under the 1023 integer
 *   maximum of LEDC's 10.8 fixed-point divider, so the fractional part is used
 *   and the 50 Hz is accurate.
 *
 *   Duty is a count out of 2^bits over the full period (2^bits == always on):
 *       duty = pulse_us * 2^14 / 20000
 *   One LSB is 20000 / 16384 = 1.22 us, an order of magnitude finer than the
 *   MG90S's own ~10 us deadband, so quantisation is not the limiting factor.
 *   Endpoints: 500 us -> 409 counts, 2400 us -> 1966 counts.
 */
static uint32_t us_to_duty(int us)
{
    return (uint32_t)(((uint64_t)us << SERVO_RES_BITS) / SERVO_PERIOD_US);
}

static int clamp_deg(int deg) { return deg < 0 ? 0 : (deg > 180 ? 180 : deg); }

/* ---- immediate setter ---- */

static bool s_ready;                 /* LEDC configured; false => every call is a no-op */
static int  s_current_deg = -1;      /* -1 until the first write */
static int  s_target_deg;

void servo_set_deg(int deg)
{
    if (!s_ready) return;
    deg = clamp_deg(deg);
    int us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * deg / 180;
    if (ledc_set_duty(SERVO_MODE, SERVO_CHANNEL, us_to_duty(us)) == ESP_OK)
        ledc_update_duty(SERVO_MODE, SERVO_CHANNEL);
    s_current_deg = deg;
}

int  servo_target_deg(void) { return s_target_deg; }
bool servo_screen_is_deployed(void)
{
    /* Nearest-endpoint classification: the sweep may still be in flight, and the
     * mechanism has no position feedback, so this reports intent, not truth. */
    int d_dep = abs(s_target_deg - CONFIG_KGN_SERVO_DEPLOYED_DEG);
    int d_ret = abs(s_target_deg - CONFIG_KGN_SERVO_RETRACTED_DEG);
    return d_dep < d_ret;
}

/* ---- sweep task ---- */

/* One PWM period per interpolation step: updating faster than the servo can be
 * re-triggered buys nothing and just burns CPU. */
#define SWEEP_STEP_MS  20
#define SERVO_Q_DEPTH  4

typedef struct { int16_t target_deg; uint16_t duration_ms; } servo_cmd_t;

static QueueHandle_t s_q;
static uint32_t s_last_cmd_ms;
static uint32_t s_dropped;      /* rate-limited or queue-full requests */

bool servo_sweep_to(int deg, uint32_t ms)
{
    if (!s_ready || !s_q) return false;
    deg = clamp_deg(deg);

    /* Rate limit before anything else. A flood of MODE_CMD datagrams must not be
     * able to reverse the MG90S continuously — that strips the plastic gearbox.
     * A repeat of the current target is dropped silently and does not count as a
     * command, so holding a mode does not keep the limiter armed. */
    if (deg == s_target_deg) return true;

    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    if (s_last_cmd_ms && (uint32_t)(now - s_last_cmd_ms) < CONFIG_KGN_SERVO_CMD_MIN_MS) {
        s_dropped++;
        return false;
    }
    s_last_cmd_ms = now;

    servo_cmd_t c = { .target_deg = (int16_t)deg,
                      .duration_ms = (uint16_t)(ms > 10000 ? 10000 : ms) };
    /* Zero timeout: this can run on the kgn_udp task and must never block it. */
    if (xQueueSend(s_q, &c, 0) != pdPASS) { s_dropped++; return false; }
    s_target_deg = deg;
    return true;
}

bool servo_screen_deploy(void)
{
    return servo_sweep_to(CONFIG_KGN_SERVO_DEPLOYED_DEG, CONFIG_KGN_SERVO_SWEEP_MS);
}

bool servo_screen_retract(void)
{
    return servo_sweep_to(CONFIG_KGN_SERVO_RETRACTED_DEG, CONFIG_KGN_SERVO_SWEEP_MS);
}

static void servo_task(void *arg)
{
    int from = s_current_deg, to = s_current_deg;
    uint32_t steps_total = 0, step = 0;

    while (1) {
        bool sweeping = (step < steps_total);
        servo_cmd_t c;
        /* Park indefinitely when idle; only poll at the step rate while moving. */
        if (xQueueReceive(s_q, &c, sweeping ? pdMS_TO_TICKS(SWEEP_STEP_MS)
                                            : portMAX_DELAY) == pdPASS) {
            /* A new command supersedes any sweep in flight, starting from
             * wherever the old one got to. No queue-drain race: the current
             * angle is the only state the interpolation needs. */
            from = s_current_deg;
            to   = clamp_deg(c.target_deg);
            steps_total = c.duration_ms / SWEEP_STEP_MS;
            step = 0;
            if (steps_total == 0) { servo_set_deg(to); continue; }
            ESP_LOGI(TAG, "sweep %d -> %d deg over %u ms", from, to,
                     (unsigned)c.duration_ms);
            continue;
        }
        if (!sweeping) continue;

        step++;
        /* Linear interpolation in integer degrees. Rounded so the final step
         * lands exactly on `to` rather than one degree short. */
        int deg = from + (int)(((int64_t)(to - from) * (int)step) / (int)steps_total);
        servo_set_deg(deg);
        if (step >= steps_total) {
            s_current_deg = to;
            if (s_dropped) {
                ESP_LOGW(TAG, "%lu servo commands dropped (rate limit / queue)",
                         (unsigned long)s_dropped);
                s_dropped = 0;
            }
        }
    }
}

void servo_ledc_start(void)
{
    ledc_timer_config_t t = {
        .speed_mode = SERVO_MODE, .timer_num = SERVO_TIMER,
        .duty_resolution = SERVO_RES, .freq_hz = SERVO_FREQ_HZ, .clk_cfg = LEDC_AUTO_CLK,
    };
    esp_err_t err = ledc_timer_config(&t);
    if (err != ESP_OK) {
        /* Fail soft: no servo is survivable, a failed boot is not. */
        ESP_LOGE(TAG, "ledc_timer_config failed (%s) — servo disabled",
                 esp_err_to_name(err));
        return;
    }
    ledc_channel_config_t c = {
        .gpio_num = CONFIG_KGN_SERVO_GPIO, .speed_mode = SERVO_MODE,
        .channel = SERVO_CHANNEL, .timer_sel = SERVO_TIMER,
        .duty = 0, .hpoint = 0,
    };
    err = ledc_channel_config(&c);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ledc_channel_config(GPIO%d) failed (%s) — servo disabled",
                 CONFIG_KGN_SERVO_GPIO, esp_err_to_name(err));
        return;
    }

    s_ready = true;
    s_target_deg = CONFIG_KGN_SERVO_RETRACTED_DEG;
    servo_set_deg(CONFIG_KGN_SERVO_RETRACTED_DEG);   /* screen stowed at boot */

    s_q = xQueueCreate(SERVO_Q_DEPTH, sizeof(servo_cmd_t));
    if (!s_q) {
        ESP_LOGW(TAG, "queue alloc failed — immediate moves only, no sweeps");
        return;
    }
    /* Priority 4: above the display (3) because a half-finished mechanical sweep
     * looks broken, below telemetry (5) and kgn_udp (6) because the link matters
     * more than the mechanism. */
    if (xTaskCreate(servo_task, "kgn_servo", 2560, NULL, 4, NULL) != pdPASS) {
        ESP_LOGW(TAG, "xTaskCreate(kgn_servo) failed — immediate moves only");
        vQueueDelete(s_q);
        s_q = NULL;
        return;
    }

    ESP_LOGI(TAG, "servo ready on GPIO%d, retracted=%d deployed=%d sweep=%dms",
             CONFIG_KGN_SERVO_GPIO, CONFIG_KGN_SERVO_RETRACTED_DEG,
             CONFIG_KGN_SERVO_DEPLOYED_DEG, CONFIG_KGN_SERVO_SWEEP_MS);
}
