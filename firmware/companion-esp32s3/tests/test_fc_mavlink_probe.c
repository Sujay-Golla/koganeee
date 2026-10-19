/* Host test using iNAV's generated upstream MAVLink headers as packet producer:
 * cc -std=c11 -I ~/inav/lib/main/MAVLink test_fc_mavlink_probe.c -lm -o /tmp/fc-probe
 */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "common/mavlink.h"
#include "../main/fc_mavlink_probe.h"
#include "../main/fc_telemetry_state.h"

static void feed(fc_mavlink_probe_t *p, const uint8_t *data, size_t n)
{
    for (size_t i = 0; i < n; ++i) fc_probe_byte(p, data[i]);
}

int main(void)
{
    fc_mavlink_probe_t p = {0};
    mavlink_message_t msg;
    uint8_t data[MAVLINK_MAX_PACKET_LEN];
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);

    status->flags = MAVLINK_STATUS_FLAG_OUT_MAVLINK1;
    mavlink_msg_heartbeat_pack(1, 1, &msg, 2, 3, 128, 0, 4);
    size_t n = mavlink_msg_to_send_buffer(data, &msg);
    assert(data[0] == 0xfe);
    feed(&p, (const uint8_t *)"noise", 5);
    feed(&p, data, 3);
    assert(p.valid == 0);
    feed(&p, data + 3, n - 3);
    assert(p.valid == 1 && p.heartbeats == 1 && p.armed);
    assert(p.sysid == 1 && p.compid == 1);

    status->flags = 0;
    mavlink_msg_attitude_pack(1, 1, &msg, 1234, 0.25f, -0.5f, 1.0f, 0, 0, 0);
    n = mavlink_msg_to_send_buffer(data, &msg);
    assert(data[0] == 0xfd && data[1] < 28); /* trailing-zero truncation */
    feed(&p, data, n);
    assert(p.valid == 2 && p.attitudes == 1);
    assert(fabsf(p.roll - 0.25f) < 0.0001f);
    assert(fabsf(p.pitch + 0.5f) < 0.0001f);
    assert(fabsf(p.yaw - 1.0f) < 0.0001f);

    data[n - 1] ^= 1;
    feed(&p, data, n);
    assert(p.valid == 2 && p.bad_crc == 1);
    data[n - 1] ^= 1;
    feed(&p, data, n);
    assert(p.valid == 3);

    mavlink_msg_system_time_pack(1, 1, &msg, 0xfefd, 1234);
    n = mavlink_msg_to_send_buffer(data, &msg);
    feed(&p, data, n);
    assert(p.valid == 3 && p.skipped == 1);

    mavlink_msg_heartbeat_pack(1, 1, &msg, 2, 3, 0, 0, 4);
    n = mavlink_msg_to_send_buffer(data, &msg);
    data[2] = 1; /* unsupported signed v2, signature bytes contain sync bytes */
    feed(&p, data, n);
    const uint8_t signature[13] = {0xfe, 0xfd};
    feed(&p, signature, sizeof(signature));
    assert(p.valid == 3 && p.skipped == 2);
    data[2] = 0;
    feed(&p, data, n);
    assert(p.valid == 4 && p.heartbeats == 2 && !p.armed);

    /* A bad length must not overflow; valid traffic recovers after the noise. */
    uint8_t garbage[600] = {0xfe, 255};
    feed(&p, garbage, sizeof(garbage));
    feed(&p, data, n);
    assert(p.valid == 5 && p.used == 0);

    mavlink_sys_status_t status_message = {0};
    status_message.voltage_battery = 4980;
    mavlink_msg_sys_status_encode(1, 1, &msg, &status_message);
    n = mavlink_msg_to_send_buffer(data, &msg);
    feed(&p, data, n);
    assert(p.valid == 6 && p.statuses == 1 && p.voltage_mv == 4980);
    status->flags = MAVLINK_STATUS_FLAG_OUT_MAVLINK1;
    mavlink_msg_sys_status_encode(1, 1, &msg, &status_message);
    n = mavlink_msg_to_send_buffer(data, &msg);
    assert(data[0] == 0xfe && data[1] == 31);
    feed(&p, data, n);
    assert(p.valid == 7 && p.statuses == 2 && p.voltage_mv == 4980);

    fc_telemetry_sample_t sample = {0};
    assert(fc_sample_state(&sample, 0).flags == 0);
    p.armed = true;
    fc_sample_update(&sample, &p, 10000000);
    kgn_drone_state_t state = fc_sample_state(&sample, 10000000);
    assert(state.flags == (KGN_DS_F_FC_LINK_UP | KGN_DS_F_ARMED |
                           KGN_DS_F_YAW_VALID | KGN_DS_F_BATT_VALID));
    assert(state.yaw_cd == 5730 && state.batt_mv == 4980);
    assert(state.x_cm == 0 && state.y_cm == 0 && state.z_cm == 0);

    /* Repeated data / unrelated frame counters must not extend sample ages. */
    fc_sample_update(&sample, &p, 12000000);
    state = fc_sample_state(&sample, 12000000);
    assert(!(state.flags & KGN_DS_F_YAW_VALID) && state.yaw_cd == 0);
    assert(state.flags & KGN_DS_F_BATT_VALID);
    state = fc_sample_state(&sample, 13000001);
    assert(state.flags == 0 && state.yaw_cd == 0 && state.batt_mv == 0);

    p.heartbeats++;
    p.attitudes++;
    p.statuses++;
    p.armed = false;
    p.yaw = NAN;
    p.voltage_mv = UINT16_MAX;
    fc_sample_update(&sample, &p, 14000000);
    state = fc_sample_state(&sample, 14000000);
    assert(state.flags == KGN_DS_F_FC_LINK_UP);
    p.statuses++;
    p.attitudes++;
    p.voltage_mv = 0;
    p.yaw = -3.14159265359f;
    fc_sample_update(&sample, &p, 14000001);
    state = fc_sample_state(&sample, 14000001);
    assert(state.yaw_cd == -18000 && !(state.flags & KGN_DS_F_BATT_VALID));
    assert(fc_sample_state(&sample, 13999999).flags == 0);

    puts("FC forwarding: voltage/yaw, validity, independent expiry and link loss passed");
    puts("FC probe: v1/v2 CRC, fragmentation, truncation, corruption, unsupported frames and recovery passed");
    return 0;
}
