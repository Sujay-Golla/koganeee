"""Offline mascot voices using Windows speech or an optional neural model.

These are generic synthesized mascot styles, not a recording or actor clone.
Raising pitch here also raises formants and playback speed deliberately. The
source speaking rate can be lowered to keep the result easy to understand.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import wave

import numpy as np

from .tts import SapiTts, TtsError, TtsUnavailable


@dataclass(frozen=True)
class VoiceStyle:
    voice: str | None
    rate: int | None
    semitones: float = 0
    buzz: float = 0
    backend: str = "sapi"
    speed: float = 1


STYLES = {
    "normal": VoiceStyle(None, None),
    "bright": VoiceStyle("Zira", 0, 3),
    "mascot": VoiceStyle("Zira", -1, 5),
    "electronic": VoiceStyle("Zira", -1, 5, .12),
    "mascot-natural": VoiceStyle("af_heart", 0, 4, backend="kokoro", speed=.90),
    "mascot-lively": VoiceStyle("af_bella", 0, 4.5, backend="kokoro", speed=.92),
}
EFFECT_VERSION = 1
NEURAL_MODEL = "kokoro-v1.0.onnx"  # Full precision: much faster on this laptop's CPU.


def resolve_style(style="normal", voice=None, rate=None):
    if style not in STYLES:
        raise ValueError(f"Unknown voice style: {style}")
    preset = STYLES[style]
    selected_voice = preset.voice if voice is None else voice
    selected_rate = preset.rate if rate is None else rate
    if selected_rate is not None and (isinstance(selected_rate, bool) or not isinstance(selected_rate, int) or not -10 <= selected_rate <= 10):
        raise ValueError("Speech rate must be an integer between -10 and 10")
    return VoiceStyle(selected_voice, selected_rate, preset.semitones, preset.buzz, preset.backend, preset.speed)


@lru_cache(maxsize=1)
def _neural_engine():
    folder = Path(__file__).resolve().parents[2]/"models/kokoro-v1.0"
    model, voices = folder/NEURAL_MODEL, folder/"voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        raise TtsUnavailable("Neural voice files missing. Run python -m kogane_base.tools.setup_kokoro_voice")
    try:
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        raise TtsUnavailable('Install the free local voice with: python -m pip install -e ".[character-voice]"') from exc
    options = rt.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = rt.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session, str(voices))


def _neural_samples(text, selected):
    speed = min(2, max(.5, selected.speed*2**((selected.rate or 0)/10)))
    # The model supplies speech phrasing and intonation. No user titles or
    # forecast facts are rewritten to create an expressive delivery.
    return _neural_engine().create(text, voice=selected.voice, speed=speed, lang="en-us")


def character_effect(samples, sample_rate, *, semitones=0, buzz=0):
    """Process mono normalized audio, preserving silence and preventing clipping."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("Expected finite mono samples")
    if not math.isfinite(semitones) or not 0 <= semitones <= 8 or not math.isfinite(buzz) or not 0 <= buzz <= .3:
        raise ValueError("Character effect is outside its supported range")
    if sample_rate < 8000:
        raise ValueError("Speech needs at least an 8 kHz sample rate")
    if not x.size:
        return x.copy()
    factor = 2**(semitones/12)
    if semitones:
        # Filter before resampling to avoid reflecting high frequencies into
        # the speech band. Taper the filter's edge instead of a hard cutoff.
        spectrum = np.fft.rfft(x)
        frequency = np.fft.rfftfreq(x.size, 1/sample_rate)
        cutoff = sample_rate/(2*factor)
        roll = np.clip((frequency-cutoff*.9)/(cutoff*.1), 0, 1)
        spectrum *= .5+.5*np.cos(np.pi*roll)
        filtered = np.fft.irfft(spectrum, n=x.size)
        positions = np.arange(max(1, round(x.size/factor)))*factor
        x = np.interp(positions, np.arange(x.size), filtered)
    if buzz:
        # Mild amplitude modulation adds a buzzy texture without injecting
        # sound during pauses. Keep most of the original voice intact.
        carrier = np.sin(2*np.pi*55*np.arange(x.size)/sample_rate)
        x = x*((1-buzz)+buzz*carrier)
    peak = float(np.max(np.abs(x)))
    if peak > .95:
        x *= .95/peak
    return np.clip(x, -1, 1)


def render_speech(text, directory, *, style="normal", voice=None, rate=None):
    """Cache by text, resolved voice/rate, style parameters and effect version."""
    from ..config import CONFIG
    selected = resolve_style(style, voice, rate)
    # Resolve the existing environment defaults before hashing, so switching
    # voices cannot accidentally reuse an earlier voice's cached reply.
    selected = VoiceStyle(CONFIG.tts_voice if selected.voice is None else selected.voice,
                          CONFIG.tts_rate if selected.rate is None else selected.rate,
                          selected.semitones, selected.buzz, selected.backend, selected.speed)
    identity = dict(text=text, style=style, settings=asdict(selected), version=EFFECT_VERSION)
    if selected.backend == "kokoro":
        identity["model"] = NEURAL_MODEL
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory/f"{style}-{digest}.wav"
    if output.exists():
        return output
    # Generate and publish atomically; interrupted generation cannot poison
    # the speech cache. Temporary sources live inside the chosen workspace.
    with tempfile.TemporaryDirectory(prefix=".voice-", dir=directory) as temporary:
        source, processed = Path(temporary)/"source.wav", Path(temporary)/"processed.wav"
        if selected.backend == "kokoro":
            samples, sample_rate = _neural_samples(text, selected)
            if len(samples) == 0:
                raise TtsError("Neural voice returned empty speech")
        else:
            SapiTts(voice=selected.voice, rate=selected.rate).synthesise(text, source)
            if not selected.semitones and not selected.buzz:
                os.replace(source, output)
                return output
            with wave.open(str(source), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                    raise TtsError("Character speech needs uncompressed 16-bit mono WAV")
                sample_rate = wav.getframerate()
                samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float)/32768
        audio = character_effect(samples, sample_rate, semitones=selected.semitones, buzz=selected.buzz)
        with wave.open(str(processed), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(np.rint(audio*32767).astype("<i2").tobytes())
        os.replace(processed, output)
    return output
