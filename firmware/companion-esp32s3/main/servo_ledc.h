#pragma once
#include <stdbool.h>
#include <stdint.h>

/* MG90S screen-rollout servo on LEDC PWM. */
void servo_ledc_start(void);

/* Immediate, blocking-free move. Clamped to 0..180. Not rate limited: this is
 * the low-level setter, used by the sweep task and by bring-up code. */
void servo_set_deg(int degrees);

/*
 * Queue a smooth sweep to `degrees` over `ms` milliseconds. Non-blocking: safe
 * to call from the UDP rx task. Returns false if the request was dropped
 * (rate limited, queue full, or servo not started).
 * ms == 0 jumps straight to the target.
 */
bool servo_sweep_to(int degrees, uint32_t ms);

/* Named positions for the retractable screen mechanism (CONFIG_KGN_SERVO_*). */
bool servo_screen_deploy(void);
bool servo_screen_retract(void);

/* Last commanded target angle, for the status screen. */
int  servo_target_deg(void);
bool servo_screen_is_deployed(void);
