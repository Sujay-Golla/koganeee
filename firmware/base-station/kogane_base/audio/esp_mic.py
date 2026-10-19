"""Live ESP32 microphone input. Sends only MIC_ON/MIC_OFF, never flight commands."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import socket
import threading
import time

from ..net.sink import SocketSink
from ..protocol import AudioCmd, AudioFmt, MsgType, audio_ctrl_payload, unpack, unpack_audio_chunk


@dataclass
class StreamStats:
    chunks: int = 0
    samples: int = 0
    lost: int = 0
    late: int = 0
    malformed: int = 0
    foreign: int = 0
    resets: int = 0


class MicOrderBuffer:
    """Reorder within 80 ms; expose gaps as decoder resets, not invented audio."""

    def __init__(self, wait=.08):
        self.wait = wait
        self.expected = None
        self.pending = {}
        self.stats = StreamStats()
        self.last_output = None

    def push(self, chunk, now):
        if chunk.start or self.expected is None:
            self.pending.clear()
            self.expected = chunk.seq
            self.stats.resets += 1
            reset = True
        else:
            reset = False
        delta = (chunk.seq-self.expected) & 0xffff
        if delta >= 32768:
            self.stats.late += 1
            return []
        if chunk.seq in self.pending:
            self.stats.late += 1
            return []
        self.pending[chunk.seq] = (now, chunk.pcm)
        if delta > 32 or len(self.pending) > 3:
            return self.flush(now, force=True)
        return self._drain(reset) + self.flush(now)

    def _drain(self, reset=False):
        result = []
        while self.expected in self.pending:
            stamp, pcm = self.pending.pop(self.expected)
            result.append((pcm, reset))
            reset = False
            self.stats.chunks += 1
            self.stats.samples += len(pcm)//2
            self.last_output = stamp
            self.expected = (self.expected+1) & 0xffff
        return result

    def flush(self, now, force=False):
        if not self.pending or (not force and now-min(p[0] for p in self.pending.values()) < self.wait):
            return []
        next_seq = min(self.pending, key=lambda seq: (seq-self.expected) & 0xffff)
        self.stats.lost += (next_seq-self.expected) & 0xffff
        self.stats.resets += 1
        self.expected = next_seq
        return self._drain(reset=True)


class EspMicInput:
    """Drain UDP continuously, including while recognition is paused for replies."""

    def __init__(self, host, callback, *, port=5005, listen_port=5005):
        self.host, self.port, self.listen_port = host, port, listen_port
        self.callback = callback
        self.order = MicOrderBuffer()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = ""
        self.last_audio = None
        self.sink = None
        self.thread = None

    @property
    def stats(self):
        return asdict(self.order.stats)

    def _control(self, command):
        if command not in (AudioCmd.MIC_ON, AudioCmd.MIC_OFF):
            raise ValueError("Microphone input only permits MIC_ON and MIC_OFF")
        self.sink.send(MsgType.AUDIO_TTS, audio_ctrl_payload(command))

    def __enter__(self):
        self.peer_ip = socket.gethostbyname(self.host)
        try:
            self.sink = SocketSink(self.peer_ip, self.port, recv=True, bind_port=self.listen_port)
            self.sink.sock.settimeout(.04)
            self._control(AudioCmd.MIC_ON)
            self.thread = threading.Thread(target=self._receive, daemon=True)
            self.thread.start()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def _deliver(self, blocks):
        for pcm, reset in blocks:
            self.callback(pcm, reset)
            self.last_audio = time.monotonic()
            self.ready.set()

    def _receive(self):
        last_retry = time.monotonic()
        try:
            while not self.stop.is_set():
                now = time.monotonic()
                if not self.ready.is_set() and now-last_retry >= 1:
                    self._control(AudioCmd.MIC_ON)
                    last_retry = now
                try:
                    data, address = self.sink.sock.recvfrom(2048)
                except socket.timeout:
                    self._deliver(self.order.flush(time.monotonic()))
                    continue
                if address != (self.peer_ip, self.port):
                    self.order.stats.foreign += 1
                    continue
                frame = unpack(data)
                if frame is None:
                    self.order.stats.malformed += 1
                    continue
                if frame.msg_type != MsgType.AUDIO_MIC:
                    continue
                chunk = unpack_audio_chunk(frame.payload)
                if chunk is None or chunk.fmt != AudioFmt.PCM_S16LE:
                    self.order.stats.malformed += 1
                    continue
                self._deliver(self.order.push(chunk, time.monotonic()))
        except Exception as exc:
            if not self.stop.is_set():
                self.error = str(exc)

    def check_health(self):
        if self.error:
            raise RuntimeError(f"Board microphone connection failed: {self.error}")
        if self.last_audio is not None and time.monotonic()-self.last_audio > 3:
            raise RuntimeError("Board microphone stream stopped. Check board power/Wi-Fi, then restart.")

    def wait_ready(self, stop=None, timeout=8):
        deadline = time.monotonic()+timeout
        while not self.ready.wait(.05):
            self.check_health()
            if stop is not None and stop.is_set():
                return False
            if time.monotonic() >= deadline:
                raise RuntimeError("No board audio received. Check laptop IP (firmware: 10.0.0.66), UDP 5005 and Windows firewall.")
        return True

    def __exit__(self, *args):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=.5)
        if self.sink:
            try:
                # UDP has no acknowledgement. Repeat the harmless OFF command
                # so a single lost packet is less likely to leave streaming on.
                for _ in range(3):
                    self._control(AudioCmd.MIC_OFF)
            except OSError:
                pass
            finally:
                self.sink.close()
