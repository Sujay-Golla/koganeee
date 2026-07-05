#pragma once
#include <stdint.h>
#include <stddef.h>

void wifi_udp_start(void);
int  wifi_udp_send(const uint8_t *frame, size_t len);
