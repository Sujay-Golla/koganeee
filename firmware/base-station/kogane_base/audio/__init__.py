"""Wire-level audio for the drone link: AUDIO_TTS (0x40) out, AUDIO_MIC (0x41) in.

This package is the transport, not the brain. `voice/` is where wakeword -> STT -> intent
-> response will live; everything here is about getting 16 kHz mono PCM onto and off the
KGN link correctly and in real time:

* `wav`      — load/convert/chunk PCM. Pure numpy + stdlib `wave`, no I/O beyond files.
* `sender`   — `AudioSender`: CTRL commands, tones, WAV playback paced to real time.
* `tts`      — speech synthesis backends. Windows SAPI via PowerShell, no pip install.
* `recorder` — `MicRecorder`: reassembles inbound 0x41 chunks and writes a WAV.
"""
from __future__ import annotations

from .recorder import MicRecorder, MicStats
from .sender import AudioSender, pcm_payloads
from .tts import SapiTts, TtsError, TtsUnavailable, default_backend, synthesise_to_wav
from .wav import (chunk_pcm, downmix, load_wav, pcm_to_bytes, resample_linear, tone,
                  to_kgn_pcm, wav_probe, write_wav)

__all__ = [
    "AudioSender", "MicRecorder", "MicStats", "SapiTts", "TtsError", "TtsUnavailable",
    "chunk_pcm", "default_backend", "downmix", "load_wav", "pcm_payloads",
    "pcm_to_bytes", "resample_linear", "synthesise_to_wav", "to_kgn_pcm", "tone",
    "wav_probe", "write_wav",
]
