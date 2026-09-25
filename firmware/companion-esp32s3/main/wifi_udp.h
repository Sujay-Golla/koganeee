#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

/* Join Wi-Fi (STA) and start the UDP rx/tx task. */
void wifi_udp_start(void);

/* Send a raw framed datagram to the base station. Thread-safe once wifi is up. */
int wifi_udp_send(const uint8_t *frame, size_t len);

/*
 * Link status, for telemetry and the status screen. Both are cheap and safe to
 * call from any task.
 */
/* Dotted-quad of the current station IP. Returns false (and writes "0.0.0.0")
 * when there is no lease yet. `n` should be >= 16. */
bool wifi_udp_get_ip_str(char *out, size_t n);

/* Current AP RSSI in dBm. Returns false when not associated. */
bool wifi_udp_get_rssi(int *rssi_dbm);
