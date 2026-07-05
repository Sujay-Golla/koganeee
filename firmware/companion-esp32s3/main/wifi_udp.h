#pragma once
#include <stdint.h>
#include <stddef.h>

/* Join Wi-Fi (STA) and start the UDP rx/tx task. */
void wifi_udp_start(void);

/* Send a raw framed datagram to the base station. Thread-safe once wifi is up. */
int wifi_udp_send(const uint8_t *frame, size_t len);
