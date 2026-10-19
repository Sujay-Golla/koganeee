/*
 * FC link (UART1 to the STM32F722 running iNAV).
 *
 * Current UART1 is dedicated to MAVLink telemetry. A separate bounded bench
 * test can issue PARAM_REQUEST_LIST to verify the reverse wire. The legacy
 * MSP control placeholder below remains blocked by CONFIG_KGN_FC_RX_ONLY.
 *
 * PCB PA9 (STM32 TX) reaches GPIO43, so ESP32 RX=43 and TX=44. The net labels
 * describe the module's default UART0 functions, not the required directions.
 * The primary console remains on native USB. RX_ONLY is the default test mode;
 * its TX pad remains an input except during the optional bounded request test.
 * Base-station setpoints are discarded in both bench modes.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "link_fc.h"
#include "wifi_udp.h"
#include "fc_mavlink_probe.h"
#include "fc_telemetry_state.h"
#include "fc_uart_request_test.h"

#if defined(CONFIG_KGN_FC_REQUEST_TEST) && !defined(CONFIG_KGN_FC_RX_ONLY)
#error "The request test requires flight-command blocking."
#endif

static const char *TAG = "link_fc";
#define FC_UART   (CONFIG_KGN_FC_UART_NUM)
#define FC_BAUD   115200

static portMUX_TYPE s_state_lock = portMUX_INITIALIZER_UNLOCKED;
static fc_telemetry_sample_t s_sample;

kgn_drone_state_t link_fc_state(void)
{
    fc_telemetry_sample_t snapshot;
    portENTER_CRITICAL(&s_state_lock);
    snapshot = s_sample;
    portEXIT_CRITICAL(&s_state_lock);
    return fc_sample_state(&snapshot, esp_timer_get_time());
}

/* The UART GPIO matrix can route the UART1 peripheral to GPIO43/44, so the port
 * number never has to change — but the console must be off those pads first. */
#if defined(CONFIG_KGN_PINS_OWNER_FC_LINK) && \
    (defined(CONFIG_ESP_CONSOLE_UART_DEFAULT) || defined(CONFIG_ESP_CONSOLE_UART_CUSTOM))
#error "FC link pins require a console on USB or no console; UART console would drive the STM32 TX net."
#endif

/* The framing/task helpers below are only called when the FC link owns the pins;
 * keep them compiled (so both configs stay type-checked) but silence the
 * unused-function noise in the console-owning build. */
#define KGN_FC_ONLY  __attribute__((unused))

/* ---- MSP v2 framing ($X<) ---- */
// TODO(kogane): implement full MSP v2 encode. Skeleton computes the header only.
#define MSP_SET_RAW_RC 200

static uint8_t msp_crc8_dvb_s2(uint8_t crc, uint8_t b)
{
    crc ^= b;
    for (int i = 0; i < 8; ++i)
        crc = (crc & 0x80) ? (crc << 1) ^ 0xD5 : (crc << 1);
    return crc;
}

static KGN_FC_ONLY void msp_send(uint16_t function, const uint8_t *payload, uint16_t size)
{
    uint8_t hdr[9];
    hdr[0]='$'; hdr[1]='X'; hdr[2]='<';
    hdr[3]=0;                        // flag
    hdr[4]=function & 0xFF; hdr[5]=function >> 8;
    hdr[6]=size & 0xFF;    hdr[7]=size >> 8;
    uint8_t crc = 0;
    for (int i = 3; i < 8; ++i) crc = msp_crc8_dvb_s2(crc, hdr[i]);
    for (uint16_t i = 0; i < size; ++i) crc = msp_crc8_dvb_s2(crc, payload[i]);
    uart_write_bytes(FC_UART, (const char *)hdr, 8);
    if (size) uart_write_bytes(FC_UART, (const char *)payload, size);
    uart_write_bytes(FC_UART, (const char *)&crc, 1);
}

/* Map a velocity/yaw setpoint onto RC channels (1000..2000us). Keep the channel
 * order identical to the FC `map`/`rc` config in fc-inav/config/kogane-fc.diff. */
static KGN_FC_ONLY uint16_t clamp_rc(int v) { return v < 1000 ? 1000 : (v > 2000 ? 2000 : (uint16_t)v); }

void link_fc_apply_setpoint(const kgn_setpoint_t *sp)
{
    if (!sp) return;
#if !defined(CONFIG_KGN_PINS_OWNER_FC_LINK) || defined(CONFIG_KGN_FC_RX_ONLY)
    /* Pins reserved or flight commands blocked during the bench test. */
    return;
#else
    // TODO(kogane): proper velocity->RC scaling + expo; this is a linear placeholder.
    uint16_t ch[8];
    ch[0] = clamp_rc(1500 + sp->vy_cms);       // roll   (A)
    ch[1] = clamp_rc(1500 + sp->vx_cms);       // pitch  (E)
    ch[2] = clamp_rc(1500 + sp->vz_cms);       // throttle (T)
    ch[3] = clamp_rc(1500 + sp->yaw_rate_cds); // yaw    (R)
    ch[4] = 1500; ch[5] = 1500; ch[6] = 1500; ch[7] = 1500; // aux
    msp_send(MSP_SET_RAW_RC, (const uint8_t *)ch, sizeof(ch));
#endif
}

static KGN_FC_ONLY void fc_task(void *arg)
{
    uint8_t rx[256];
    fc_mavlink_probe_t probe = {0};
    fc_telemetry_sample_t sample = {0};
    int64_t last_log = 0;
    uint32_t last_bytes = 0;
#if defined(CONFIG_KGN_FC_REQUEST_TEST)
    fc_request_test_t request = {.start_us = esp_timer_get_time()};
#endif
    while (1) {
        int n = uart_read_bytes(FC_UART, rx, sizeof(rx), pdMS_TO_TICKS(20));
        if (n > 0) {
            int64_t received_us = esp_timer_get_time();
            for (int i = 0; i < n; ++i) {
                fc_probe_byte(&probe, rx[i]);
                fc_sample_update(&sample, &probe, received_us);
            }
            portENTER_CRITICAL(&s_state_lock);
            s_sample = sample;
            portEXIT_CRITICAL(&s_state_lock);
        }
        int64_t now = esp_timer_get_time();
#if defined(CONFIG_KGN_FC_REQUEST_TEST)
        kgn_drone_state_t state = fc_sample_state(&sample, now);
        bool ready = (state.flags & KGN_DS_F_FC_LINK_UP) && !(state.flags & KGN_DS_F_ARMED);
        fc_request_action_t action = fc_request_tick(&request, &probe, ready, now);
        if (action == FC_REQUEST_SEND) {
            uint8_t frame[10];
            size_t size = fc_request_frame(frame, request.attempts - 1,
                                           request.target_system, request.target_component);
            esp_err_t err = uart_set_pin(FC_UART, CONFIG_KGN_FC_UART_TX,
                                         CONFIG_KGN_FC_UART_RX,
                                         UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
            if (err != ESP_OK || uart_write_bytes(FC_UART, frame, size) != (int)size) {
                request.done = true;
                action = FC_REQUEST_FAIL;
            } else {
                ESP_LOGI(TAG, "FC request test: PARAM_REQUEST_LIST attempt %u/3 -> sys=%u comp=%u",
                         request.attempts, request.target_system, request.target_component);
            }
        }
        if (action == FC_REQUEST_PASS || action == FC_REQUEST_FAIL) {
            ESP_ERROR_CHECK(gpio_reset_pin(CONFIG_KGN_FC_UART_TX));
            ESP_ERROR_CHECK(gpio_set_direction(CONFIG_KGN_FC_UART_TX, GPIO_MODE_INPUT));
            if (action == FC_REQUEST_PASS)
                ESP_LOGI(TAG, "FC request test PASS: CRC-valid PARAM_VALUE reply; TX=GPIO%d returned INPUT; flight commands blocked",
                         CONFIG_KGN_FC_UART_TX);
            else
                ESP_LOGW(TAG, "FC request test FAIL: no matching reply or no fresh disarmed FC; TX=GPIO%d returned INPUT; flight commands blocked",
                         CONFIG_KGN_FC_UART_TX);
        }
#endif
        if (now - last_log >= 2000000) {
            ESP_LOGI(TAG, "FC RX: bytes=%lu (+%lu/2s) valid=%lu heartbeat=%lu attitude=%lu bad_crc=%lu skipped=%lu",
                     (unsigned long)probe.bytes, (unsigned long)(probe.bytes - last_bytes),
                     (unsigned long)probe.valid, (unsigned long)probe.heartbeats,
                     (unsigned long)probe.attitudes, (unsigned long)probe.bad_crc,
                     (unsigned long)probe.skipped);
            if (probe.attitudes)
                ESP_LOGI(TAG, "FC attitude: roll=%.1f pitch=%.1f yaw=%.1f deg; sys=%u comp=%u",
                         probe.roll * 57.2957795, probe.pitch * 57.2957795,
                         probe.yaw * 57.2957795, probe.sysid, probe.compid);
            last_log = now;
            last_bytes = probe.bytes;
        }
        /* telemetry.c publishes a fresh snapshot independently of UART timing. */
    }
}

void link_fc_start(void)
{
#if !defined(CONFIG_KGN_PINS_OWNER_FC_LINK)
    /* Console owns GPIO43/44: bringing the FC UART up here would fight stdout on
     * the same pads, so stay completely off the bus. */
    ESP_LOGW(TAG, "FC link disabled: GPIO43/44 reserved "
                  "(TX=%d RX=%d). Select CONFIG_KGN_PINS_OWNER_FC_LINK=y "
                  "with the console on USB to start the UART.",
             CONFIG_KGN_FC_UART_TX, CONFIG_KGN_FC_UART_RX);
    return;
#else
    uart_config_t uc = {
        .baud_rate = FC_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
#if defined(CONFIG_KGN_FC_RX_ONLY)
    ESP_ERROR_CHECK(gpio_reset_pin(CONFIG_KGN_FC_UART_TX));
    ESP_ERROR_CHECK(gpio_set_direction(CONFIG_KGN_FC_UART_TX, GPIO_MODE_INPUT));
    const int tx_pin = UART_PIN_NO_CHANGE;
#else
    const int tx_pin = CONFIG_KGN_FC_UART_TX;
#endif
    ESP_ERROR_CHECK(uart_driver_install(FC_UART, 2048, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(FC_UART, &uc));
    ESP_ERROR_CHECK(uart_set_pin(FC_UART, tx_pin, CONFIG_KGN_FC_UART_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    if (xTaskCreate(fc_task, "fc_link", 4096, NULL, 7, NULL) != pdPASS) {
        ESP_LOGE(TAG, "FC diagnostic task creation failed");
        uart_driver_delete(FC_UART);
        return;
    }
#if defined(CONFIG_KGN_FC_RX_ONLY)
#if defined(CONFIG_KGN_FC_REQUEST_TEST)
    ESP_LOGI(TAG, "FC REQUEST TEST UART%d: RX=GPIO%d TX=GPIO%d @%d; bounded read query only; flight commands blocked",
             FC_UART, CONFIG_KGN_FC_UART_RX, CONFIG_KGN_FC_UART_TX, FC_BAUD);
#else
    ESP_LOGI(TAG, "FC RX-ONLY UART%d: RX=GPIO%d @%d; TX=GPIO%d left INPUT; commands blocked",
             FC_UART, CONFIG_KGN_FC_UART_RX, FC_BAUD, CONFIG_KGN_FC_UART_TX);
#endif
#else
    ESP_LOGI(TAG, "FC link up on UART%d (TX=%d RX=%d)", FC_UART,
             CONFIG_KGN_FC_UART_TX, CONFIG_KGN_FC_UART_RX);
#endif
#endif
}
