"""The speaker fallback should play locally without contacting the drone."""

import wave
from pathlib import Path

from kogane_base.tools import say_cli


def test_say_defaults_to_laptop_without_network(monkeypatch):
    class StubTts:
        last_voice = "test"

        def __init__(self, **_kwargs):
            pass

        def synthesise(self, text, out_path):
            assert text == "Hello Kogane"
            with wave.open(str(out_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 160)
            return Path(out_path)

    played = []
    monkeypatch.setattr(say_cli, "SapiTts", StubTts)
    monkeypatch.setattr(say_cli, "_play_local", lambda path: played.append(Path(path)))
    monkeypatch.setattr(say_cli, "SocketSink",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("local speech contacted the drone")))

    assert say_cli.main(["Hello", "Kogane"]) == 0
    assert len(played) == 1
    assert played[0].suffix == ".wav"
