import queue
import socket
import sys
import threading
from types import SimpleNamespace

import pytest

from kogane_base.audio import esp_mic
from kogane_base.protocol import (AudioCmd, MsgType, AU_F_START, audio_pcm_payload,
                                  pack, unpack_audio_chunk)
from kogane_base.tools import demo_assistant as demo


def chunk(seq, start=False):
    return unpack_audio_chunk(audio_pcm_payload(bytes([seq & 255, 0])*512, seq=seq, flags=AU_F_START if start else 0))


def test_reordering_duplicates_rollover_and_missing_packet_reset():
    order = esp_mic.MicOrderBuffer()
    assert order.push(chunk(65535, True), 0) == [(chunk(65535).pcm, True)]
    assert order.push(chunk(1), .032) == []
    assert order.push(chunk(0), .04) == [(chunk(0).pcm, False), (chunk(1).pcm, False)]
    assert order.push(chunk(1), .05) == []
    assert order.stats.late == 1
    assert order.push(chunk(3), .06) == []
    assert order.flush(.1) == []
    assert order.flush(.15) == [(chunk(3).pcm, True)]
    assert order.stats.lost == 1
    assert order.stats.samples == 4*512
    # A reboot's START explicitly discards an old pending fragment.
    order.push(chunk(5), .16)
    assert order.push(chunk(0, True), .17) == [(chunk(0).pcm, True)]
    assert order.pending == {}


def test_large_backlog_is_bounded_and_never_fills_missing_audio_with_invented_samples():
    order = esp_mic.MicOrderBuffer()
    order.push(chunk(0, True), 0)
    assert order.push(chunk(40), .1) == [(chunk(40).pcm, True)]
    assert order.stats.lost == 39 and len(order.pending) == 0


def test_input_accepts_only_configured_peer_valid_audio_and_shuts_down_stream(monkeypatch):
    incoming, delivered, sent = queue.Queue(), [], []
    ready = threading.Event()
    def datagram(msg_type, seq=0):
        return pack(msg_type, audio_pcm_payload(b'\x12\x00'*512, seq=seq, flags=AU_F_START if seq == 0 else 0), seq, 1)
    class Sink:
        def __init__(self, *args, **kwargs):
            self.sock = self
            self.closed = False
        def settimeout(self, value):
            pass
        def recvfrom(self, size):
            try:
                return incoming.get(timeout=.01)
            except queue.Empty:
                raise socket.timeout()
        def send(self, msg_type, payload):
            sent.append((msg_type, unpack_audio_chunk(payload).cmd))
        def close(self):
            self.closed = True
    monkeypatch.setattr(esp_mic, "SocketSink", Sink)
    monkeypatch.setattr(socket, "gethostbyname", lambda _: "127.0.0.1")
    incoming.put((datagram(MsgType.AUDIO_MIC), ("127.0.0.2", 5005)))
    incoming.put((datagram(MsgType.AUDIO_MIC), ("127.0.0.1", 5010)))
    incoming.put((b"bad CRC or header", ("127.0.0.1", 5005)))
    incoming.put((datagram(MsgType.AUDIO_TTS), ("127.0.0.1", 5005)))
    incoming.put((datagram(MsgType.AUDIO_MIC), ("127.0.0.1", 5005)))
    def capture(pcm, reset):
        delivered.append((pcm, reset))
        ready.set()
    with esp_mic.EspMicInput("board", capture) as source:
        assert source.wait_ready(timeout=.5)
        assert ready.wait(.5)
        source.check_health()
        with pytest.raises(ValueError):
            source._control(AudioCmd.SELFTEST)
    assert delivered == [(b'\x12\x00'*512, True)]
    assert source.stats["foreign"] == 2 and source.stats["malformed"] == 1
    assert sent == [(MsgType.AUDIO_TTS, AudioCmd.MIC_ON)]+[(MsgType.AUDIO_TTS, AudioCmd.MIC_OFF)]*3
    assert source.sink.closed and not source.thread.is_alive()


def test_missing_or_stopped_stream_is_an_error_not_a_laptop_fallback(monkeypatch):
    source = esp_mic.EspMicInput("board", lambda *a: None)
    with pytest.raises(RuntimeError, match="No board audio"):
        source.wait_ready(timeout=0)
    source.last_audio = 0
    with pytest.raises(RuntimeError, match="stream stopped"):
        source.check_health()
    assert demo.parser().parse_args([]).mic_source == "laptop"
    with pytest.raises(ValueError, match="--mic-host"):
        demo.main(["--mic-source", "esp32", "--headless"])
    with pytest.raises(ValueError, match="--device"):
        demo.main(["--mic-source", "esp32", "--mic-host", "board", "--device", "3"])


def test_board_worker_feeds_existing_decoder_without_opening_laptop_audio(tmp_path, monkeypatch):
    received, commands, stop = [], queue.Queue(), threading.Event()
    (tmp_path/"am").mkdir()
    monkeypatch.setitem(sys.modules, "vosk", SimpleNamespace(Model=lambda _: None, SetLogLevel=lambda _: None))
    def forbidden(*args, **kwargs):
        pytest.fail("Board mode opened the laptop microphone")
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=forbidden))
    class Decoder:
        results = []
        rejection = None
        def __init__(self, *args):
            pass
        def reset(self):
            pass
        def tick(self, now):
            return []
        def feed(self, pcm, now):
            received.append(pcm)
            stop.set()
            return [("voice", "show me my tasks for today")]
    class Input:
        def __init__(self, host, callback, **kwargs):
            assert host == "board"
            self.callback = callback
        def __enter__(self):
            self.callback(b'\x12\x00'*512, True)
            return self
        def __exit__(self, *args):
            pass
        def wait_ready(self, stop):
            return True
        def check_health(self):
            pass
    monkeypatch.setattr(esp_mic, "EspMicInput", Input)
    monkeypatch.setattr(demo, "SpeechDecoder", Decoder)
    demo.voice_worker(tmp_path, commands, threading.Event(), stop, mic_source="esp32", mic_host="board")
    assert received == [b'\x12\x00'*512]
    assert list(commands.queue)[-1] == ("voice", "show me my tasks for today")
    assert not any(event[0] == "error" for event in commands.queue)
