import wave

import numpy as np
import pytest

from kogane_base.audio import character_voice as cv
from kogane_base.tools import demo_assistant as demo


def test_pitch_is_raised_by_the_requested_interval_without_clipping():
    rate = 16000
    signal = .5*np.sin(2*np.pi*400*np.arange(rate)/rate)
    output = cv.character_effect(signal, rate, semitones=5)
    spectrum = np.abs(np.fft.rfft(output))
    frequency = np.fft.rfftfreq(output.size, 1/rate)[np.argmax(spectrum)]
    assert frequency == pytest.approx(400*2**(5/12), abs=2)
    assert output.size == round(rate/2**(5/12))
    assert np.max(np.abs(output)) <= .95
    assert np.all(cv.character_effect(np.zeros(rate), rate, semitones=5, buzz=.12) == 0)


def test_cache_distinguishes_voice_style_rate_and_text_and_preserves_wav_format(tmp_path, monkeypatch):
    calls = []
    class Tts:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def synthesise(self, text, path):
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                audio = (12000*np.sin(2*np.pi*400*np.arange(1600)/16000)).astype("<i2")
                wav.writeframes(audio.tobytes())
    monkeypatch.setattr(cv, "SapiTts", Tts)
    mascot = cv.render_speech("Task saved", tmp_path, style="mascot")
    assert calls == [dict(voice="Zira", rate=-1)]
    assert cv.render_speech("Task saved", tmp_path, style="mascot") == mascot
    assert len(calls) == 1
    paths = {mascot, cv.render_speech("Task saved", tmp_path, style="bright"),
             cv.render_speech("Task saved", tmp_path, style="mascot", voice="David"),
             cv.render_speech("Task saved", tmp_path, style="mascot", rate=1),
             cv.render_speech("Forecast ready", tmp_path, style="mascot")}
    assert len(paths) == 5
    with wave.open(str(mascot), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.getnframes() == round(1600/2**(5/12))
    assert not list(tmp_path.glob(".voice-*"))


def test_failed_synthesis_does_not_publish_a_cache_entry(tmp_path, monkeypatch):
    class Tts:
        def __init__(self, **kwargs):
            pass
        def synthesise(self, text, path):
            path.write_bytes(b"incomplete")
            raise RuntimeError("Voice unavailable")
    monkeypatch.setattr(cv, "SapiTts", Tts)
    with pytest.raises(RuntimeError):
        cv.render_speech("Hello", tmp_path, style="mascot")
    assert list(tmp_path.iterdir()) == []


def test_assistant_passes_selected_style_to_weather_and_tasks_cache(tmp_path, monkeypatch):
    calls = []
    def render(text, directory, **kwargs):
        calls.append((text, directory, kwargs))
        return directory/"voice.wav"
    monkeypatch.setattr(cv, "render_speech", render)
    monkeypatch.setattr(demo, "BASE", tmp_path)
    for kind in ("tasks", "weather"):
        demo.prepare_speech(kind, "Hello", style="mascot", voice="Zira", rate=-1)
    assert all(args == ("Hello", tmp_path/"outputs/speech", dict(style="mascot", voice="Zira", rate=-1)) for args in calls)
    args = demo.parser().parse_args(["--speech-style", "mascot", "--tts-rate", "-1"])
    assert args.speech_style == "mascot" and args.tts_rate == -1


@pytest.mark.parametrize("style,voice", [("mascot-natural", "af_heart"), ("mascot-lively", "af_bella")])
def test_neural_styles_keep_reply_text_and_use_native_audio_without_windows_speech(tmp_path, monkeypatch, style, voice):
    calls = []
    class Engine:
        def create(self, text, **kwargs):
            calls.append((text, kwargs))
            return .5*np.sin(2*np.pi*400*np.arange(2400)/24000), 24000
    monkeypatch.setattr(cv, "_neural_engine", lambda: Engine())
    def no_windows(**kwargs):
        pytest.fail("A selected neural style must not silently use Windows speech")
    monkeypatch.setattr(cv, "SapiTts", no_windows)
    words = 'Task 3: Buy milk & bread. High 17, low 4.'
    result = cv.render_speech(words, tmp_path, style=style)
    assert calls[0][0] == words
    assert calls[0][1]["voice"] == voice and calls[0][1]["lang"] == "en-us"
    with wave.open(str(result), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        assert np.any(audio) and np.max(np.abs(audio.astype(int))) < 32767
    assert cv.render_speech(words, tmp_path, style=style) == result
    assert len(calls) == 1
    assert demo.parser().parse_args(["--speech-style", style]).speech_style == style


def test_neural_failure_does_not_publish_or_fall_back_to_an_old_voice(tmp_path, monkeypatch):
    def missing():
        raise cv.TtsUnavailable("Model missing")
    monkeypatch.setattr(cv, "_neural_engine", missing)
    with pytest.raises(cv.TtsUnavailable, match="Model missing"):
        cv.render_speech("Task saved", tmp_path, style="mascot-lively")
    assert list(tmp_path.iterdir()) == []
