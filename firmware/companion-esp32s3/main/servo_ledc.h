#pragma once
/* MG90S screen-rollout servo on LEDC PWM. */
void servo_ledc_start(void);
void servo_set_deg(int degrees);   /* 0..180 */
