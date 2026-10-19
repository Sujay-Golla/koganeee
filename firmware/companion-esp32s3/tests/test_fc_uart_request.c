/* Compile with -I ~/inav/lib/main/MAVLink and -lm. */
#include <assert.h>
#include <stdio.h>
#include "common/mavlink.h"
#include "../main/fc_uart_request_test.h"

int main(void)
{
    uint8_t expected[MAVLINK_MAX_PACKET_LEN], actual[10];
    mavlink_message_t msg;
    mavlink_status_t *status = mavlink_get_channel_status(MAVLINK_COMM_0);
    for (uint8_t seq = 0; seq < 3; ++seq) {
        status->flags = MAVLINK_STATUS_FLAG_OUT_MAVLINK1;
        status->current_tx_seq = seq;
        mavlink_msg_param_request_list_pack(255, 190, &msg, 42, 1);
        size_t len = mavlink_msg_to_send_buffer(expected, &msg);
        assert(len == fc_request_frame(actual, seq, 42, 1));
        assert(memcmp(actual, expected, len) == 0);
        assert(actual[5] == MAVLINK_MSG_ID_PARAM_REQUEST_LIST);
    }

    fc_mavlink_probe_t probe = {.heartbeat_sysid = 42, .heartbeat_compid = 1};
    fc_request_test_t test = {.start_us = 100};
    assert(fc_request_tick(&test, &probe, false, 100) == FC_REQUEST_IDLE);
    assert(test.attempts == 0);
    assert(fc_request_tick(&test, &probe, true, 200) == FC_REQUEST_SEND);
    assert(test.attempts == 1 && test.target_system == 42);
    assert(fc_request_tick(&test, &probe, true, 201) == FC_REQUEST_IDLE);

    /* An unrelated component's valid reply must not pass the test. */
    status->flags = 0;
    mavlink_param_value_t reply = {0};
    mavlink_msg_param_value_encode(42, 2, &msg, &reply);
    size_t len = mavlink_msg_to_send_buffer(expected, &msg);
    for (size_t i = 0; i < len; ++i) fc_probe_byte(&probe, expected[i]);
    assert(probe.parameters == 1);
    assert(fc_request_tick(&test, &probe, true, 300) == FC_REQUEST_IDLE);

    /* iNAV intentionally returns an empty parameter list, including v2 truncation. */
    /* Same empty-list pack call used by iNAV's request handler. */
    mavlink_msg_param_value_pack(42, 1, &msg, 0, 0, 0, 0, 0);
    len = mavlink_msg_to_send_buffer(expected, &msg);
    assert(expected[1] == 1);
    for (size_t i = 0; i < len; ++i) fc_probe_byte(&probe, expected[i]);
    assert(probe.parameters == 2);
    assert(fc_request_tick(&test, &probe, true, 400) == FC_REQUEST_PASS);
    assert(fc_request_tick(&test, &probe, true, 500) == FC_REQUEST_IDLE);

    test = (fc_request_test_t){0};
    assert(fc_request_tick(&test, &probe, true, 0) == FC_REQUEST_SEND);
    assert(fc_request_tick(&test, &probe, true, 2000000) == FC_REQUEST_SEND);
    assert(fc_request_tick(&test, &probe, true, 4000000) == FC_REQUEST_SEND);
    assert(test.attempts == 3);
    assert(fc_request_tick(&test, &probe, true, 6000000) == FC_REQUEST_FAIL);
    assert(fc_request_tick(&test, &probe, true, 8000000) == FC_REQUEST_IDLE);

    test = (fc_request_test_t){0};
    assert(fc_request_tick(&test, &probe, false, 14999999) == FC_REQUEST_IDLE);
    assert(fc_request_tick(&test, &probe, false, 15000000) == FC_REQUEST_FAIL);
    assert(test.attempts == 0);

    test = (fc_request_test_t){0};
    assert(fc_request_tick(&test, &probe, true, 0) == FC_REQUEST_SEND);
    assert(fc_request_tick(&test, &probe, false, 100) == FC_REQUEST_FAIL);
    puts("FC request: upstream encoding, matching CRC-valid reply, retry bound and heartbeat gate passed");
    return 0;
}
