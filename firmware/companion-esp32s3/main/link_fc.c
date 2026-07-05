/*
 * FC link (UART1 to the STM32F722 running iNAV).
 *
 * Two protocols share this UART (see shared/PROTOCOL.md §2):
 *   - INBOUND  : iNAV MAVLink v2 telemetry  -> parse into DRONE_STATE, forward to base.
 *   - OUTBOUND : MSP v2 RC override          -> inject off-board setpoints as RC channels.
 *
 * iNAV does NOT accept MAVLink setpoints, which is why control uses MSP.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"

#include "link_fc.h"
#include "wifi_udp.h"

static const char *TAG = "link_fc";
#define FC_UART   (CONFIG_KGN_FC_UART_NUM)
#define FC_BAUD   115200

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

static void msp_send(uint16_t function, const uint8_t *payload, uint16_t size)
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
static uint16_t clamp_rc(int v) { return v < 1000 ? 1000 : (v > 2000 ? 2000 : (uint16_t)v); }

void link_fc_apply_setpoint(const kgn_setpoint_t *sp)
{
    if (!sp) return;
    // TODO(kogane): proper velocity->RC scaling + expo; this is a linear placeholder.
    uint16_t ch[8];
    ch[0] = clamp_rc(1500 + sp->vy_cms);       // roll   (A)
    ch[1] = clamp_rc(1500 + sp->vx_cms);       // pitch  (E)
    ch[2] = clamp_rc(1500 + sp->vz_cms);       // throttle (T)
    ch[3] = clamp_rc(1500 + sp->yaw_rate_cds); // yaw    (R)
    ch[4] = 1500; ch[5] = 1500; ch[6] = 1500; ch[7] = 1500; // aux
    msp_send(MSP_SET_RAW_RC, (const uint8_t *)ch, sizeof(ch));
}

/* ---- MAVLink telemetry parse (inbound) ---- */
static void parse_mavlink(const uint8_t *buf, int n)
{
    // TODO(kogane): run bytes through a MAVLink v2 parser; on ATTITUDE/SYS_STATUS/
    // LOCAL_POSITION_NED, fill a kgn_drone_state_t and wifi_udp_send() it as DRONE_STATE.
    (void)buf; (void)n;
}

static void fc_task(void *arg)
{
    uint8_t rx[256];
    while (1) {
        int n = uart_read_bytes(FC_UART, rx, sizeof(rx), pdMS_TO_TICKS(20));
        if (n > 0) parse_mavlink(rx, n);
        // TODO(kogane): periodic DRONE_STATE heartbeat to base even without telemetry.
    }
}

void link_fc_start(void)
{
    uart_config_t uc = {
        .baud_rate = FC_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(FC_UART, 1024, 1024, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(FC_UART, &uc));
    ESP_ERROR_CHECK(uart_set_pin(FC_UART, CONFIG_KGN_FC_UART_TX, CONFIG_KGN_FC_UART_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    xTaskCreate(fc_task, "fc_link", 4096, NULL, 7, NULL);
    ESP_LOGI(TAG, "FC link up on UART%d", FC_UART);
}
