/*
 * MG90S screen-rollout servo (LEDC 50 Hz PWM). Presets: SCREEN_HIDDEN / SCREEN_VISIBLE.
 * This one is functional enough to move a servo; tune min/max pulse to your mechanism.
 */
#include "driver/ledc.h"
#include "esp_log.h"
#include "servo_ledc.h"

static const char *TAG = "servo_ledc";

#define SERVO_TIMER     LEDC_TIMER_0
#define SERVO_MODE      LEDC_LOW_SPEED_MODE
#define SERVO_CHANNEL   LEDC_CHANNEL_0
#define SERVO_RES       LEDC_TIMER_14_BIT   // 16384 counts
#define SERVO_FREQ_HZ   50                  // 20 ms period
#define SERVO_MIN_US    500                 // ~0 deg  (tune)
#define SERVO_MAX_US    2400                // ~180 deg (tune)

static uint32_t us_to_duty(int us)
{
    // duty = counts * (pulse_us / period_us); period = 20000us at 50Hz
    return (uint32_t)(((uint64_t)us * ((1 << 14) - 1)) / 20000);
}

void servo_set_deg(int deg)
{
    if (deg < 0) deg = 0; if (deg > 180) deg = 180;
    int us = SERVO_MIN_US + (SERVO_MAX_US - SERVO_MIN_US) * deg / 180;
    ledc_set_duty(SERVO_MODE, SERVO_CHANNEL, us_to_duty(us));
    ledc_update_duty(SERVO_MODE, SERVO_CHANNEL);
}

void servo_ledc_start(void)
{
    ledc_timer_config_t t = {
        .speed_mode = SERVO_MODE, .timer_num = SERVO_TIMER,
        .duty_resolution = SERVO_RES, .freq_hz = SERVO_FREQ_HZ, .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&t);
    ledc_channel_config_t c = {
        .gpio_num = CONFIG_KGN_SERVO_GPIO, .speed_mode = SERVO_MODE,
        .channel = SERVO_CHANNEL, .timer_sel = SERVO_TIMER,
        .duty = 0, .hpoint = 0,
    };
    ledc_channel_config(&c);
    servo_set_deg(0);   // SCREEN_HIDDEN at boot
    ESP_LOGI(TAG, "servo ready on GPIO%d", CONFIG_KGN_SERVO_GPIO);
}
