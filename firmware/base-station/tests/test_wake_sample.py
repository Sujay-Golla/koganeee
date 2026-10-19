"""Pronunciation recording is bounded, local and preserves existing samples."""
import json
import sys
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from kogane_base.tools import wake_sample


def test_recorder_writes_exact_bounded_mono_wav_and_never_overwrites(tmp_path, monkeypatch):
    calls = []

    class Stream:
        def __init__(self, **kwargs):
            assert kwargs["samplerate"] == 16000 and kwargs["channels"] == 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, count):
            calls.append(count)
            return np.full(count, 1234, dtype="<i2").tobytes(), False

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=Stream))
    path = tmp_path/"sample.wav"
    wake_sample.record_sample(path, .25)
    with wave.open(str(path)) as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        assert wav.getsampwidth() == 2 and wav.getnframes() == 4000
    assert calls == [1600, 1600, 800]
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        wake_sample.record_sample(path, .25)
    assert path.read_bytes() == original


def test_analysis_cli_does_not_open_mic_or_modify_aliases(tmp_path, monkeypatch, capsys):
    path = tmp_path/"existing.wav"
    path.write_bytes(b"existing sample")
    monkeypatch.setattr(wake_sample, "record_sample", lambda *a, **kw: pytest.fail("opened microphone"))
    report = dict(unconstrained=[dict(text="coggan")], wake_grammar=[dict(text="coggan")],
                  events=[("wake", "coggan")], peak_fraction=.2, clipped_fraction=0)
    monkeypatch.setattr(wake_sample, "analyze_sample", lambda *a: report)
    assert wake_sample.main(["--analyze", str(path)]) == 0
    assert path.read_bytes() == b"existing sample"
    assert json.loads(path.with_suffix(".recognition.json").read_text())["events"] == [["wake", "coggan"]]
    assert "no model has been trained or changed" in capsys.readouterr().out
