#pragma once
#include <stdbool.h>
#include <stdint.h>

/*
 * I2S audio: INMP441 mic capture (-> base as AUDIO_MIC) and speaker playback
 * (<- base as AUDIO_TTS). One I2S controller in full duplex; see audio_i2s.c for
 * the topology and its constraints.
 *
 * THE SPEAKER PATH IS OFF BY DEFAULT. CONFIG_KGN_AUDIO_TX_ENABLE defaults to n,
 * which means no I2S TX channel is allocated, CONFIG_KGN_I2S_DOUT is parked LOW
 * into U11 (MAX98357A), and the mic's RX channel becomes the clock master. The
 * API below is unchanged either way: AUDIO_TTS is accepted and discarded rather
 * than refused. See the TX gate note at the top of audio_i2s.c for why.
 */

/* Bring up the enabled directions and start the audio tasks. Fails soft: every
 * error logs once and returns, leaving wifi/udp/telemetry/display/servo
 * untouched. */
void audio_i2s_start(void);

/*
 * Hand one AUDIO_TTS (0x40) payload over for playback. Copies and queues; never
 * touches I2S. Safe (and intended) to call from the kgn_udp rx task: it never
 * blocks, and on a full queue it drops the OLDEST queued chunk rather than this
 * one. Returns false if the chunk was rejected or a drop occurred.
 *
 * Also handles fmt 2 (CTRL) chunks, which is how the base turns mic streaming on
 * and off and fires the self-test tone.
 */
bool audio_submit_tts(const uint8_t *payload, uint16_t len);

/* Request the speaker self-test tone sequence. Non-blocking: sets a flag the
 * playback task picks up. Returns false, with an explanatory log line, if the TX
 * path is gated off (CONFIG_KGN_AUDIO_TX_ENABLE=n) or did not come up. */
bool audio_selftest_tone(void);

/* Mic -> base streaming gate. OFF at boot unless CONFIG_KGN_MIC_STREAM_ON_BOOT. */
void audio_mic_stream_set(bool on);
bool audio_mic_stream_get(void);

/* Last computed capture RMS, 0..32767 in 16-bit PCM units. 0 when the mic is not
 * running. Cheap and safe from any task. */
uint16_t audio_mic_level(void);
