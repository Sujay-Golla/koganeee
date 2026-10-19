"""Offline voice, live weather and local tasks; optional ESP32 mic, no flight commands."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from functools import lru_cache
import json
import math
from pathlib import Path
import queue
import re
import threading
import time

from ..protocol import MsgType, rgb565
from ..screen.frames import image_to_rgb565
from ..screen.sender import ScreenSender
from .task_list import SHOW_TASKS, TaskStore, TaskBoard, parse_task_command
from .weather import WeatherClient, WeatherError

BASE = Path(__file__).resolve().parents[2]
DEFAULT_SPEECH_STYLE = "mascot-natural"
WEATHER_PHRASES = ("show me the weather today", "show me the weather", "what is the weather today", "weather")
STOP_PHRASES = ("stop listening", "stop task editing")
PHRASES = [*WEATHER_PHRASES, *SHOW_TASKS, *STOP_PHRASES, "next page", "previous page", "undo last change", "undo", "[unk]"]
# The English Vosk model has no 'kogane' lexicon entry. These existing phonetic
# spellings let it recognize the spoken name without pretending a custom wake
# model was trained. Match complete phrases/prefixes, never arbitrary substrings.
WAKE_ALIASES = ("kogane", "kogan", "cogan", "coggan", "ko gane")
DEFAULT_WAKE_PROFILE = BASE / "calib" / "wake_pronunciation.json"


def command_intent(text: str) -> str | None:
    clean = normalise(text)
    if clean.startswith("kogane "):
        clean = clean[7:]
    if clean in WEATHER_PHRASES:
        return "weather"
    if clean in STOP_PHRASES:
        return "stop"
    if parse_task_command(clean) is not None:
        return "tasks"
    return None


def normalise(text):
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", text.lower()).split())


class WakeSession:
    """One wake opens one bounded command window; every answer consumes it."""

    def __init__(self, aliases=WAKE_ALIASES, timeout_s=12, thresholds=None):
        self.aliases = sorted({normalise(a) for a in aliases if normalise(a)}, key=len, reverse=True)
        self.timeout_s, self.until = timeout_s, 0
        self.thresholds = thresholds or {}

    def reset(self):
        self.until = 0

    def tick(self, now):
        if self.until and now >= self.until:
            self.reset()
            return [("timeout", "")]
        return []

    def accept(self, text, confidence, now):
        events = self.tick(now)
        clean = normalise(text)
        alias = next((a for a in self.aliases if clean == a or clean.startswith(a+" ")), None)
        if alias is not None and confidence >= self.thresholds.get(alias, .65):
            self.until = now+self.timeout_s
            events.append(("wake", text))
            clean = clean[len(alias):].strip()
        if self.until and command_intent(clean) and confidence >= .55:
            self.reset()
            events.append(("voice", clean))
        return events


def recognition_grammar(model, aliases=WAKE_ALIASES):
    available = list(dict.fromkeys(a for a in aliases if a and
                                  all(model.vosk_model_find_word(w) >= 0 for w in a.split())))
    if not available:
        raise RuntimeError("No wake-name spelling exists in this model; supply an English --wake-alias")
    commands = [p for p in PHRASES if p != "[unk]"]
    return json.dumps([*available, *commands,
                       *(f"{wake} {command}" for wake in available for command in commands), "[unk]"])


class SpeechConditioner:
    """Streaming DC/rumble removal and bounded gain for the laptop microphone."""

    def __init__(self, gain=4):
        import numpy as np
        if not math.isfinite(gain) or not 1 <= gain <= 12:
            raise ValueError("Microphone gain must be between 1 and 12")
        self.gain = gain
        taps = np.arange(257)-128
        low = 2*80/16000*np.sinc(2*80/16000*taps)*np.hamming(257)
        self.kernel = -low/low.sum()
        self.kernel[128] += 1
        self.history = None

    def reset(self):
        self.history = None

    def process(self, data):
        import numpy as np
        samples = np.frombuffer(data, dtype="<i2").astype(np.float64)
        if not len(samples):
            return b""
        if self.history is None:
            self.history = np.full(256, samples[0])
        padded = np.concatenate((self.history, samples))
        self.history = padded[-256:].copy()
        filtered = np.convolve(padded, self.kernel, mode="valid")*self.gain
        return np.clip(np.rint(filtered), -32768, 32767).astype("<i2").tobytes()


class SpeechDecoder:
    """Parallel name/command decoding; exact names alone may open a wake session."""

    def __init__(self, model, aliases=WAKE_ALIASES, timeout_s=12, thresholds=None,
                 mic_gain=4, recognizer_factory=None):
        if recognizer_factory is None:
            from vosk import KaldiRecognizer
            recognizer_factory = KaldiRecognizer
        self.session = WakeSession(aliases, timeout_s, thresholds)
        joint = recognition_grammar(model, aliases)
        names = list(dict.fromkeys(a for a in aliases if a and
                     all(model.vosk_model_find_word(w) >= 0 for w in a.split())))
        self.joint = recognizer_factory(model, 16000, joint)
        self.names = recognizer_factory(model, 16000, json.dumps([*names, "[unk]"]))
        self.free = recognizer_factory(model, 16000)
        self.joint.SetWords(True)
        self.names.SetWords(True)
        self.free.SetWords(True)
        self.conditioner = SpeechConditioner(mic_gain)
        self.results = []
        self.last_command = (0, "")
        self.task_until = 0
        self.rejection = None

    def reset(self):
        self.joint.Reset()
        self.names.Reset()
        self.free.Reset()
        self.conditioner.reset()
        self.session.reset()
        self.last_command = (0, "")
        self.task_until = 0
        self.rejection = None

    def begin_tasks(self, now, seconds=30):
        self.session.reset()
        self.task_until = now+seconds

    def _accept_command(self, text, confidence, now):
        intent = command_intent(text)
        if not intent:
            return []
        if confidence < .55:
            self.rejection = ("low_confidence", text)
            return []
        if not self.session.until:
            if self.task_until and intent in ("tasks", "stop"):
                self.session.until = self.task_until
            else:
                self.rejection = ("wake_required", text)
                return []
        events = self.session.accept(text, confidence, now)
        if any(event[0] == "voice" for event in events):
            self.task_until = 0
        return events

    def tick(self, now):
        events = self.session.tick(now)
        if self.task_until and now >= self.task_until:
            self.task_until = 0
            events.append(("task_timeout", ""))
        return events

    def feed(self, data, now):
        chunk = self.conditioner.process(data)
        events = self.tick(now)
        self.results = []
        self.rejection = None
        for mode, rec in (("command", self.free), ("joint", self.joint), ("name", self.names)):
            if not rec.AcceptWaveform(chunk):
                continue
            result = json.loads(rec.Result())
            self.results.append((mode, result))
            words = result.get("result", [])
            confidence = sum(w.get("conf", 0) for w in words)/max(1, len(words))
            text = result.get("text", "")
            if mode == "command":
                self.last_command = (now, text)
                # Free speech is essential for task titles: a fixed phrase
                # grammar would discard them or guess a different command.
                clean = normalise(text)
                alias = next((a for a in self.session.aliases if clean.startswith(a+" ")), None)
                if alias:
                    clean = clean[len(alias):].strip()
                events.extend(self._accept_command(clean, confidence, now))
            elif mode == "joint" and not any(event[0] == "voice" for event in events):
                clean = normalise(text)
                alias = next((a for a in self.session.aliases if clean == a or clean.startswith(a+" ")), None)
                if alias is not None:
                    clean = clean[len(alias):].strip()
                    task = parse_task_command(clean)
                    # Only general speech may edit tasks. In particular, never
                    # let the constrained decoder invent a title or number.
                    if not self.session.until:
                        if task and task.action not in ("show", "next", "previous"):
                            events.extend(self.session.accept(alias, confidence, now))
                        else:
                            events.extend(self.session.accept(text, confidence, now))
                elif (self.session.until or self.task_until) and clean in PHRASES:
                    # Fixed viewing/undo phrases retain their accurate grammar.
                    # Never substitute one while a new task title is being said.
                    partial = json.loads(getattr(self.free, "PartialResult", lambda: '{}')()).get("partial", "")
                    recent = self.last_command[1] if now-self.last_command[0] < 1.5 else ""
                    undo = clean in ("undo", "undo last change")
                    editing = re.compile(r"\b(new|rename|complete|finish|delete|remove|mark)\b" if undo else
                                         r"\b(new|rename|change|complete|finish|delete|remove|mark|undo)\b")
                    if confidence >= (.75 if undo else .55) and not editing.search(partial+" "+recent):
                        events.extend(self._accept_command(clean, confidence, now))
            elif (not self.session.until and
                  not any(event[0] in ("wake", "voice") for event in events) and
                  normalise(text) in self.session.aliases):
                # Reject partial names and names embedded in other words/sentences.
                events.extend(self.session.accept(text, confidence, now))
        if any(event[0] == "voice" for event in events):
            # A delayed endpoint from the name decoder must not re-open the session.
            self.names.Reset()
            self.free.Reset()
            self.rejection = None
        if any(event[0] == "wake" for event in events):
            self.task_until = 0
            self.rejection = None
        return events


def load_wake_profile(path=None):
    source = Path(path) if path else DEFAULT_WAKE_PROFILE
    if not source.exists():
        if path:
            raise FileNotFoundError(f"Wake profile not found: {source}")
        return (), {}
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("type") != "kogane.wake_profile" or data.get("version") != 1:
        raise ValueError("Unsupported wake profile format")
    aliases = tuple(normalise(value) for value in data.get("aliases", []) if isinstance(value, str))
    thresholds = {}
    for alias, value in data.get("min_confidence", {}).items():
        key, confidence = normalise(alias), float(value)
        if key not in (*WAKE_ALIASES, *aliases) or not math.isfinite(confidence) or not .25 <= confidence <= 1:
            raise ValueError("Wake profile needs a named alias and confidence between 0.25 and 1")
        thresholds[key] = confidence
    return aliases, thresholds


class DisplayOnlySink:
    """Reject any future accidental attempt to send control/audio packets here."""

    def __init__(self, sink):
        self.sink = sink

    def send(self, msg_type, payload):
        if int(msg_type) != int(MsgType.SCREEN_FRAME):
            raise ValueError("Demo transport permits SCREEN_FRAME only")
        self.sink.send(msg_type, payload)


@lru_cache(maxsize=256)
def font(size, bold=False):
    from PIL import ImageFont
    win = Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(win), size) if win.exists() else ImageFont.load_default(size=size)


def panel_text(draw, box, value, size, *, fill="#292d29", bold=False):
    """Fit one prominent line into logical LCD bounds, without clipping glyphs."""
    value = str(value)
    left, top, right, bottom = box
    for chosen in range(size, 13, -1):
        face = font(chosen, bold)
        x0, y0, x1, y1 = face.getbbox(value)
        if x1-x0 <= right-left and y1-y0 <= bottom-top:
            break
    while value and x1-x0 > right-left:
        value = value[:-2].rstrip()+"…" if len(value) > 2 else ""
        x0, y0, x1, y1 = face.getbbox(value)
    draw.text(((left+right-x1+x0)/2-x0, (top+bottom-y1+y0)/2-y0),
              value, font=face, fill=fill)


def task_title_lines(value, width=254):
    face = font(24)
    words, lines = value.split(), []
    while words and len(lines) < 2:
        line = words.pop(0)
        while words and face.getlength(line+" "+words[0]) <= width:
            line += " "+words.pop(0)
        if face.getlength(line) > width or (len(lines) == 1 and words):
            while line and face.getlength(line+"…") > width:
                line = line[:-1]
            line = line.rstrip()+"…"
        lines.append(line)
    return lines


def card(kind, *, city="Toronto", weather_report=None, weather_error="", mic_source="laptop",
         keyboard=False, size=(320, 240), task_items=(), task_page=0, task_notice="", task_active=False):
    from PIL import Image
    from .mapping_ui import DensityDraw
    if size[0]*3 != size[1]*4 or min(size) < 1:
        raise ValueError("Assistant cards use a 4:3 aspect ratio")
    if kind.endswith("_keyboard"):
        kind, keyboard = kind.removesuffix("_keyboard"), True
    paper, ink, muted, accent = "#f6f4ef", "#292d29", "#686d64", "#ad4f35"
    img = Image.new("RGB", size, "#e8efe8" if kind in ("listening", "listening_demo") else paper)
    scale = size[0]/320
    d = DensityDraw(img, scale)
    if kind == "weather":
        panel_text(d, (8, 5, 312, 36), (weather_report.city if weather_report else city).upper(), 26, fill=accent, bold=True)
        if weather_report:
            panel_text(d, (8, 38, 312, 56), "Now", 17, fill=muted)
            panel_text(d, (8, 57, 312, 146), f"{weather_report.temperature_c:.0f}°C", 98, bold=True)
            panel_text(d, (8, 150, 312, 182), weather_report.condition, 28)
            panel_text(d, (8, 187, 312, 216), f"Today  ↑{weather_report.high_c:.0f}°  ↓{weather_report.low_c:.0f}°", 24)
            updated = weather_report.updated_local[11:16]
            panel_text(d, (8, 221, 312, 239), f"Open-Meteo · {updated}" + (" · Keyboard" if keyboard else ""), 14, fill=muted)
        else:
            panel_text(d, (8, 72, 312, 116), "Weather", 48, bold=True)
            panel_text(d, (8, 119, 312, 161), "unavailable" if weather_error else "Not loaded", 38, fill=accent)
            panel_text(d, (8, 189, 312, 224), "Check internet" if weather_error else "Ask for today's forecast", 23, fill=muted)
    elif kind == "weather_loading":
        panel_text(d, (8, 15, 312, 50), city.upper(), 26, fill=accent, bold=True)
        panel_text(d, (8, 85, 312, 148), "Checking…", 54, bold=True)
        if keyboard:
            panel_text(d, (8, 216, 312, 237), "KEYBOARD", 16, fill=muted)
    elif kind == "tasks":
        panel_text(d, (8, 5, 312, 39), "Today", 30, bold=True)
        d.line((10, 41, 310, 41), fill="#dedfd7")
        pages = max(1, (len(task_items)+2)//3)
        page = max(0, min(task_page, pages-1))
        if not task_items:
            panel_text(d, (8, 83, 312, 145), "No tasks", 46, fill=muted)
        for row, task in enumerate(task_items[page*3:page*3+3]):
            top = 48+row*52
            color = "#687b69" if task["done"] else ink
            d.rectangle((10, top+8, 34, top+32), outline=color if task["done"] else "#b1b7ab", width=2)
            if task["done"]:
                d.line((14, top+20, 20, top+26, 30, top+14), fill=color, width=3)
            for j, line in enumerate(task_title_lines(f"{task['id']}. {task['text']}")):
                face = font(24)
                bbox = face.getbbox(line)
                y = top+2+j*25
                d.text((52, y-bbox[1]), line, font=face, fill=color)
                if task["done"]:
                    d.line((52, y+9, 52+face.getlength(line), y+9), fill=color)
        if task_notice:
            panel_text(d, (8, 201, 312, 217), task_notice, 16, fill=accent)
        color = "#466853" if task_active else muted
        d.ellipse((12, 226, 18, 232), fill=color)
        d.text((26, 219), "Keyboard demo" if keyboard else "Listening" if task_active else "Say Kogane",
               font=font(17), fill=color)
        if pages > 1:
            panel_text(d, (238, 220, 312, 239), f"{page+1}/{pages}", 17, fill=muted)
    elif kind in ("listening", "listening_demo"):
        for i, height in enumerate((18, 32, 46, 32, 18)):
            x = 128+i*16
            d.line((x, 52-height/2, x, 52+height/2), fill="#466853", width=6)
        # Keep the heading inside the quick-update strip used by PanelOutput.
        panel_text(d, (8, 96, 312, 144), "Listening…", 58, fill="#365c43", bold=True)
        if kind == "listening_demo":
            panel_text(d, (8, 216, 312, 237), "KEYBOARD DEMO", 19, fill="#466853")
    elif kind == "error":
        panel_text(d, (8, 42, 312, 100), "Microphone", 50, bold=True)
        panel_text(d, (8, 106, 312, 160), "unavailable", 48, fill=accent, bold=True)
        panel_text(d, (8, 189, 312, 229), "Check board / Wi-Fi" if mic_source == "esp32" else "Check laptop input", 26, fill=muted)
    elif kind == "starting":
        panel_text(d, (8, 78, 312, 147), "Starting…", 64, bold=True)
    elif kind == "rehearsal":
        panel_text(d, (8, 24, 312, 72), "Keyboard", 52, bold=True)
        panel_text(d, (8, 88, 312, 131), "A  Listening", 34)
        panel_text(d, (8, 137, 312, 181), "W  Weather", 34)
        panel_text(d, (8, 186, 312, 230), "T  Tasks", 34)
    else:
        panel_text(d, (8, 28, 312, 72), "Say", 36, fill=accent)
        panel_text(d, (8, 87, 312, 158), "Kogane", 82, bold=True)
    return img


class PanelOutput:
    def __init__(self, host, port, *, rotation=0, mirror_x=False):
        self.host, self.port = host, port
        self.rotation = rotation
        self.mirror_x = mirror_x
        self.lock = threading.Lock()
        self.pixels = None
        self.revision = 0
        self.sent_revision = 0  # local transmit completion, not an LCD acknowledgement
        self.listening = False
        self.error = ""
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def set_frame(self, image, *, listening=False):
        if self.rotation == 180:
            from PIL import Image
            image = image.transpose(Image.Transpose.ROTATE_180)
        if self.mirror_x:
            from PIL import Image
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        with self.lock:
            self.pixels = image_to_rgb565(image)
            self.listening = listening
            self.revision += 1
        self.changed.set()

    def _run(self):
        if not self.host:
            return
        from ..net.sink import SocketSink
        try:
            with SocketSink(self.host, self.port) as raw:
                sender = ScreenSender(DisplayOnlySink(raw), strip_delay_s=0.012)
                shown, last_full = -1, -math.inf
                try:
                    while not self.stop.is_set():
                        self.changed.clear()
                        with self.lock:
                            pixels, rev, listening = self.pixels, self.revision, self.listening
                        if pixels is not None:
                            if rev != shown or time.monotonic()-last_full > 8:
                                if listening and rev != shown:
                                    # Tiny text packet gives immediate feedback before
                                    # the paced RGB repaint reaches the main heading.
                                    if self.rotation == 180 or self.mirror_x:
                                        # Firmware text cannot be rotated remotely.
                                        # Send the already-rotated heading band first.
                                        stride = 320*2
                                        sender.send_rgb565(pixels[96*stride:144*stride],
                                                           w=320, h=48, y0=96, clear=False)
                                    else:
                                        sender.send_text("LISTENING...", row=3, scale=3,
                                                         fg=rgb565(54, 92, 67), bg=rgb565(232, 239, 232))
                                sender.send_rgb565(pixels, clear=not listening)
                                shown, self.sent_revision = rev, rev
                                last_full = time.monotonic()
                            else:
                                sender.send_rgb565(pixels[-2:], w=1, h=1, x0=319, y0=239, clear=False)
                        self.changed.wait(1.0)
                finally:
                    sender.release()
        except Exception as exc:
            self.error = str(exc)
            print(f"LCD transport error: {exc}", flush=True)


def voice_worker(model_path, commands, paused, stop, device=None, timeout_s=12, aliases=WAKE_ALIASES, thresholds=None, mic_gain=4,
                 task_mode=None, rearm=None, task_session_seconds=30, mic_source="laptop", mic_host=None,
                 mic_port=5005, mic_listen_port=5005):
    try:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        if not (model_path / "am").is_dir():
            raise RuntimeError(f"Speech model missing: {model_path}. See DEMO_TODAY.md.")
        model = Model(str(model_path))
        decoder = SpeechDecoder(model, aliases, timeout_s, thresholds, mic_gain)
        audio = queue.Queue(maxsize=8 if mic_source == "esp32" else 64)

        def capture_pcm(pcm, reset=False):
            if paused.is_set():
                return
            if audio.full():
                if mic_source != "esp32":
                    return
                # Prefer current audio to delayed commands. A discontinuity
                # cancels the old wake/session rather than joining cut words.
                while not audio.empty():
                    try:
                        audio.get_nowait()
                    except queue.Empty:
                        break
                reset = True
            try:
                audio.put_nowait((pcm, reset))
            except queue.Full:
                pass

        def capture(indata, frames, timestamp, status):
            capture_pcm(bytes(indata))

        with ExitStack() as inputs:
            board_input = None
            if mic_source == "esp32":
                from ..audio.esp_mic import EspMicInput
                board_input = inputs.enter_context(EspMicInput(mic_host, capture_pcm, port=mic_port, listen_port=mic_listen_port))
                if not board_input.wait_ready(stop):
                    return
                print(f"Board microphone receiving: {mic_host}; laptop recognizer ready", flush=True)
            else:
                import sounddevice as sd
                inputs.enter_context(sd.RawInputStream(samplerate=16000, blocksize=1600, device=device,
                                                       dtype="int16", channels=1, callback=capture))
            commands.put(("ready", "Say Kogane, then wait for Listening on the LCD"))
            was_paused = False
            first_block = True
            while not stop.is_set():
                if board_input:
                    board_input.check_health()
                if paused.is_set():
                    decoder.reset()
                    while not audio.empty():
                        try:
                            audio.get_nowait()
                        except queue.Empty:
                            break
                    was_paused = True
                    stop.wait(0.05)
                    continue
                if was_paused or (rearm is not None and rearm.is_set()):
                    decoder.reset()
                    while not audio.empty():
                        try:
                            audio.get_nowait()
                        except queue.Empty:
                            break
                    was_paused = False
                    if rearm is not None:
                        rearm.clear()
                    if task_mode is not None and task_mode.is_set():
                        decoder.begin_tasks(time.monotonic(), task_session_seconds)
                        commands.put(("task_ready", "Listening for task commands"))
                    else:
                        commands.put(("armed", "Waiting for Kogane"))
                for event in decoder.tick(time.monotonic()):
                    if event[0] == "task_timeout" and task_mode is not None:
                        task_mode.clear()
                    commands.put(event)
                try:
                    chunk, discontinuity = audio.get(timeout=0.2)
                except queue.Empty:
                    continue
                if discontinuity:
                    decoder.reset()
                    if not first_block:
                        if task_mode is not None:
                            task_mode.clear()
                        commands.put(("input_reset", "Audio interrupted / Say Kogane again"))
                first_block = False
                decoded = decoder.feed(chunk, time.monotonic())
                for mode, result in decoder.results:
                    text = result.get("text", "")
                    words = result.get("result", [])
                    confidence = (sum(w.get("conf", 0) for w in words) / len(words)) if words else 0
                    print(f"Heard ({mode}): {text!r} / confidence {confidence:.2f}", flush=True)
                for event in decoded:
                    commands.put(event)
                if decoder.rejection is not None:
                    reason, text = decoder.rejection
                    print(f"Not executed ({reason}): {text!r}", flush=True)
                    commands.put((reason, text))
    except Exception as exc:
        commands.put(("error", f"MIC ERROR: {exc}"))
        print(f"Voice unavailable: {exc}", flush=True)


def prepare_speech(kind, text, *, style=DEFAULT_SPEECH_STYLE, voice=None, rate=None):
    from ..audio.character_voice import render_speech
    return render_speech(text, BASE/"outputs/speech", style=style, voice=voice, rate=rate)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", help="ESP32 Wi-Fi IP; omit for laptop preview only")
    p.add_argument("--port", type=int, default=5005)
    p.add_argument("--lcd-rotation", type=int, choices=[0, 180], default=180,
                   help="rotate transmitted LCD cards; 180 corrects this panel's two-axis inversion")
    p.add_argument("--lcd-mirror-x", action=argparse.BooleanOptionalAction, default=True,
                   help="mirror LCD cards horizontally after rotation; enabled for this panel")
    p.add_argument("--city", default="Toronto")
    p.add_argument("--country", default="CA", help="two-letter country code for weather location (default CA)")
    p.add_argument("--tasks-file", type=Path, help="local daily task storage; defaults to data/tasks.json")
    p.add_argument("--model", type=Path, default=BASE / "models" / "vosk-model-small-en-us-0.15")
    p.add_argument("--device", type=int, help="sounddevice input index")
    p.add_argument("--mic-source", choices=["laptop", "esp32"], default="laptop", help="default laptop; esp32 is the stationary board-microphone test")
    p.add_argument("--mic-host", help="ESP32 IP for board audio; defaults to --host; does not enable LCD output")
    p.add_argument("--mic-listen-port", type=int, default=5005, help="local board-audio receive port (firmware sends to 5005)")
    p.add_argument("--mic-gain", type=float, default=4, help="gain after microphone DC/rumble removal (1-12; default 4)")
    p.add_argument("--listen-seconds", type=float, default=12, help="command window after Kogane")
    p.add_argument("--task-session-seconds", type=float, default=30, help="task-only follow-up window after replies (5-120; default 30)")
    p.add_argument("--wake-alias", action="append", default=[], help="extra phonetic spelling for the English recognizer")
    p.add_argument("--wake-profile", type=Path, help="personal pronunciation settings; defaults to calib/wake_pronunciation.json if present")
    p.add_argument("--list-mics", action="store_true")
    p.add_argument("--no-mic", action="store_true", help="keyboard rehearsal; labelled as keyboard input")
    p.add_argument("--mute", action="store_true")
    from ..audio.character_voice import STYLES
    p.add_argument("--speech-style", choices=STYLES, default=DEFAULT_SPEECH_STYLE,
                   help="offline voice style (default mascot-natural); compare with kogane_base.tools.voice_preview")
    p.add_argument("--tts-voice", help="base voice override: Windows name or Kokoro voice ID for neural styles")
    p.add_argument("--tts-rate", type=int, choices=range(-10, 11), metavar="-10..10", help="source speech rate override")
    p.add_argument("--preview", type=Path, help="save card previews and exit, without audio/network")
    p.add_argument("--seconds", type=float, default=0)
    p.add_argument("--headless", action="store_true", help="run without the laptop preview window")
    return p


def assistant_window_size(window):
    import cv2
    try:
        _, _, width, height = cv2.getWindowImageRect(window)
        if width > 0 and height > 0:
            ratio = min(1, 3840/width, 2160/height)
            return max(320, round(width*ratio)), max(240, round(height*ratio))
    except cv2.error:
        pass
    return 960, 720


def preview_card_size(size):
    unit = max(1, int(min(size[0]/4, size[1]/3)))
    return unit*4, unit*3


def assistant_preview(current, status, transcript, host, error, *, size=(1280, 720), details=False):
    import numpy as np
    from PIL import Image, ImageDraw
    import textwrap
    canvas = Image.new("RGB", size, current.getpixel((0, 0)))
    target = preview_card_size(size)
    image = current if current.size == target else current.resize(target, Image.Resampling.LANCZOS)
    canvas.paste(image, ((size[0]-target[0])//2, (size[1]-target[1])//2))
    if details or error:
        draw = ImageDraw.Draw(canvas)
        text_size = max(16, round(min(size[0]/960, size[1]/720)*20))
        face = font(text_size)
        line_height = text_size+8
        lines = ([status, transcript, f"LCD: {host or 'laptop preview only'}",
                  "Q Close | F Fullscreen | D Hide details | R Resend | H Mirror"] if details else [])
        if error:
            lines.append("LCD connection error — see terminal")
        width_chars = max(20, int((size[0]-32)/(text_size*.58)))
        lines = [part for line in lines for part in textwrap.wrap(line, width_chars)][:7]
        top = max(0, size[1]-len(lines)*line_height-20)
        draw.rectangle((0, top, size[0], size[1]), fill="#f6f4ef")
        for i, line in enumerate(lines):
            draw.text((16, top+8+i*line_height), line, font=face,
                      fill="#ad4f35" if error and i == len(lines)-1 else "#292d29")
    return np.asarray(canvas)[:, :, ::-1].copy()


def main(argv=None):
    args = parser().parse_args(argv)
    if not math.isfinite(args.listen_seconds) or not 3 <= args.listen_seconds <= 60:
        raise ValueError("--listen-seconds must be between 3 and 60")
    if not math.isfinite(args.mic_gain) or not 1 <= args.mic_gain <= 12:
        raise ValueError("--mic-gain must be between 1 and 12")
    if not math.isfinite(args.task_session_seconds) or not 5 <= args.task_session_seconds <= 120:
        raise ValueError("--task-session-seconds must be between 5 and 120")
    if args.list_mics:
        import sounddevice as sd
        print(sd.query_devices())
        return 0
    if args.mic_source == "esp32" and not args.no_mic and not args.preview:
        if not (args.mic_host or args.host):
            raise ValueError("Board microphone needs --mic-host 10.0.0.47 (or --host)")
        if args.device is not None:
            raise ValueError("Use --device only with the laptop microphone; omit it for --mic-source esp32")
    profile_aliases, thresholds = load_wake_profile(args.wake_profile)
    board = TaskBoard(TaskStore(args.tasks_file or BASE/"data/tasks.json"))
    task_mode, rearm = threading.Event(), threading.Event()
    task_active = False
    task_feedback = ""
    weather_client = WeatherClient(args.city, args.country)
    weather_report, weather_error, weather_revision = None, "", 0

    def render_card(kind, size=(320, 240)):
        return card(kind, city=args.city, weather_report=weather_report, weather_error=weather_error, mic_source=args.mic_source,
                    size=size, task_items=board.store.items(), task_page=board.page,
                    task_notice=task_feedback, task_active=task_active)

    cards = {kind: render_card(kind) for kind in
             ("starting", "ready", "listening", "listening_demo", "weather", "tasks", "error",
              "rehearsal", "weather_keyboard", "weather_loading", "weather_loading_keyboard", "tasks_keyboard")}
    if args.preview:
        args.preview.mkdir(parents=True, exist_ok=True)
        for kind, image in cards.items():
            image.save(args.preview / f"{kind}.png")
        print(args.preview.resolve())
        return 0

    from .dashboard_display import enable_dpi_awareness
    if not args.headless:
        enable_dpi_awareness()
    import cv2
    commands = queue.Queue()
    stop, paused = threading.Event(), threading.Event()
    panel = PanelOutput(args.host, args.port, rotation=args.lcd_rotation, mirror_x=args.lcd_mirror_x)
    current_kind = "rehearsal" if args.no_mic else "starting"
    current = cards[current_kind]
    panel.set_frame(current)
    panel.thread.start()
    status = "Keyboard rehearsal / microphone off" if args.no_mic else "Preparing voice recognition"
    voice_thread = None
    aliases = (*WAKE_ALIASES, *profile_aliases, *(normalise(a) for a in args.wake_alias))
    if thresholds:
        print(f"Pronunciation settings loaded: {thresholds}", flush=True)
    if not args.no_mic:
        voice_thread = threading.Thread(target=voice_worker,
            args=(args.model, commands, paused, stop, args.device, args.listen_seconds, aliases, thresholds,
                  args.mic_gain, task_mode, rearm, args.task_session_seconds, args.mic_source,
                  args.mic_host or args.host, args.port, args.mic_listen_port), daemon=True)
        voice_thread.start()
    transcript = "Say Kogane, wait for Listening, then say your command."
    spoken, pending, last_answer = None, None, None
    wake_started, keyboard_until = -math.inf, 0

    def show(kind):
        nonlocal current, current_kind
        current_kind = kind
        current = render_card(kind) if kind.startswith(("tasks", "weather")) else cards[kind]
        panel.set_frame(current, listening=kind in ("listening", "listening_demo"))

    def resume_input():
        rearm.set()
        paused.clear()

    def speak(words, kind="tasks"):
        try:
            path = prepare_speech(kind, words, style=args.speech_style, voice=args.tts_voice, rate=args.tts_rate)
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception as exc:
            print(f"Laptop playback error: {exc}", flush=True)
        finally:
            time.sleep(.35)
            resume_input()

    def fetch_weather(source, words):
        try:
            report, error = weather_client.get_today(), ""
        except WeatherError as exc:
            report, error = None, str(exc)
        except Exception as exc:
            # Always deliver a result so an unexpected provider failure cannot
            # leave the microphone paused indefinitely.
            report, error = None, f"Could not load weather: {exc}"
        if not stop.is_set():
            commands.put(("weather_result", (source, words, report, error)))

    start = time.monotonic()
    log_path = BASE / "outputs" / "assistant_events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("Say Kogane, wait for Listening, then ask for weather or your tasks for today.", flush=True)
    print("Tasks: New task buy groceries / Complete task one / Rename task number one to charge the battery / Delete task one / Undo last change.", flush=True)
    print(f"Voice is offline; weather uses Open-Meteo for {args.city}, {args.country} (internet required); tasks stay local. Q quit; A/W/T are labelled keyboard rehearsal.", flush=True)
    print(f"LCD destination: {args.host or 'none / laptop preview only'}", flush=True)
    print(f"Microphone: {'off / keyboard rehearsal' if args.no_mic else 'board / '+str(args.mic_host or args.host) if args.mic_source == 'esp32' else 'laptop'}", flush=True)
    window, fullscreen, details = "Kogane | Voice assistant", False, False
    preview_key, preview_image = None, None
    if not args.headless:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
        cv2.resizeWindow(window, 960, 720)
        print("F fullscreen; D details; Q close; R resend; H mirror; A/W/T keyboard rehearsal.", flush=True)
    try:
        with log_path.open("a", encoding="utf-8") as events:
            while not stop.is_set():
                now = time.monotonic()
                try:
                    source, words = commands.get_nowait()
                    if source == "ready":
                        status = words
                        show("ready")
                    elif source == "input_reset":
                        task_mode.clear()
                        task_active = False
                        status = words
                        show(last_answer or "ready")
                    elif source == "armed":
                        status = "Waiting for Kogane"
                    elif source == "weather_result":
                        origin, utterance, weather_report, weather_error = words
                        weather_revision += 1
                        last_answer = "weather_keyboard" if origin == "keyboard" else "weather"
                        show(last_answer)
                        reply = (weather_report.spoken() if weather_report else
                                 "Weather is unavailable. Please check the laptop internet connection and try again.")
                        print(f"Weather: {reply}" + (f" ({weather_error})" if weather_error else ""), flush=True)
                        events.write(json.dumps({"time": time.time(), "input": origin,
                                                 "text": utterance, "intent": "weather",
                                                 "microphone": args.mic_source,
                                                 "content": "Open-Meteo forecast" if weather_report else "weather unavailable",
                                                 "weather": asdict(weather_report) if weather_report else None,
                                                 "error": weather_error or None})+"\n")
                        events.flush()
                        status = "Replying / microphone paused" if not args.mute else "Waiting for Kogane"
                        if not args.mute:
                            spoken = threading.Thread(target=speak, args=(reply, "weather"), daemon=True)
                            spoken.start()
                        else:
                            resume_input()
                    elif source == "task_ready":
                        if task_mode.is_set() and not paused.is_set():
                            task_active = True
                            status = "Listening for task commands"
                            if last_answer and last_answer.startswith("tasks"):
                                show(last_answer)
                    elif source == "error":
                        status = words
                        pending = None
                        show("error")
                    elif source in ("wake", "keyboard_wake") and pending is None and not paused.is_set():
                        task_active = False
                        wake_started = now
                        keyboard_until = now+args.listen_seconds if source == "keyboard_wake" else 0
                        status = "Keyboard listening rehearsal" if source == "keyboard_wake" else "Listening for your command"
                        transcript = "KEYBOARD: listening test" if source == "keyboard_wake" else "VOICE: Kogane"
                        show("listening_demo" if source == "keyboard_wake" else "listening")
                        events.write(json.dumps({"time": time.time(), "input": source, "text": words,
                                                 "microphone": args.mic_source,
                                                 "event": "wake"})+"\n")
                        events.flush()
                    elif source in ("timeout", "task_timeout"):
                        task_mode.clear()
                        task_active = False
                        task_feedback = ""
                        status = "Timed out / Say Kogane to try again"
                        show(last_answer or "ready")
                    elif source in ("wake_required", "low_confidence"):
                        status = ("Command heard / Say Kogane first" if source == "wake_required" else
                                  "Command unclear / Please repeat")
                        if last_answer and last_answer.startswith("tasks"):
                            board.notice = "Say Kogane first" if source == "wake_required" else "Please repeat the command"
                            task_feedback = "" if source == "wake_required" else board.notice
                            board.revision += 1
                            show(last_answer)
                        events.write(json.dumps({"time": time.time(), "event": "ignored",
                                                 "reason": source, "text": words})+"\n")
                        events.flush()
                    elif source in ("voice", "keyboard") and pending is None and not paused.is_set():
                        intent = command_intent(words)
                        if intent:
                            task_feedback = ""
                            task_active = False
                            if intent == "tasks":
                                task_mode.set()
                            else:
                                task_mode.clear()
                            paused.set()
                            # Preserve a visible listening state even for a combined
                            # wake + command utterance. Spoken two-step input is preferred.
                            pending = (source, words, intent, max(now, wake_started+1.8) if source == "voice" else now)
                except queue.Empty:
                    pass
                if keyboard_until and now >= keyboard_until and pending is None:
                    keyboard_until = 0
                    status = "Keyboard rehearsal / microphone off" if args.no_mic else "Waiting for Kogane"
                    show(last_answer or ("rehearsal" if args.no_mic else "ready"))
                if pending and now >= pending[3]:
                    source, words, intent, _ = pending
                    pending, keyboard_until = None, 0
                    transcript = f"{'VOICE' if source == 'voice' else 'KEYBOARD'}: {words}"
                    task_reply = None
                    task_error = None
                    if intent == "weather":
                        weather_report, weather_error = None, ""
                        weather_revision += 1
                        status = "Checking today's forecast / microphone paused"
                        show("weather_loading_keyboard" if source == "keyboard" else "weather_loading")
                        threading.Thread(target=fetch_weather, args=(source, words), daemon=True).start()
                        continue
                    if intent == "tasks":
                        try:
                            task_reply = board.handle(words)
                            print(f"Task action: {board.notice or task_reply}", flush=True)
                        except (ValueError, OSError) as exc:
                            task_error = str(exc)
                            board.notice = str(exc) if isinstance(exc, ValueError) else "Could not save tasks"
                            task_feedback = board.notice
                            board.revision += 1
                            task_reply = board.notice
                            print(f"Task update failed: {exc}", flush=True)
                    if intent == "stop":
                        task_reply = "Task listening stopped. Say Kogane when you need me."
                        task_active = False
                        board.notice = "Listening stopped"
                        board.revision += 1
                        last_answer = "tasks_keyboard" if source == "keyboard" else "tasks"
                    else:
                        last_answer = intent+"_keyboard" if source == "keyboard" else intent
                    show(last_answer)
                    will_speak = not args.mute and task_reply is not None
                    status = "Replying / microphone paused" if will_speak else "Waiting for Kogane"
                    events.write(json.dumps({"time": time.time(), "input": source,
                                             "microphone": args.mic_source,
                                             "text": words, "intent": intent,
                                             "content": "local tasks",
                                             "error": task_error})+"\n")
                    events.flush()
                    if will_speak and (spoken is None or not spoken.is_alive()):
                        spoken = threading.Thread(target=speak, args=(task_reply,), daemon=True)
                        spoken.start()
                    else:
                        resume_input()
                if not args.headless:
                    size = assistant_window_size(window)
                    key = (current_kind, preview_card_size(size), board.revision, task_active, weather_revision)
                    if key != preview_key:
                        preview_image = render_card(current_kind, size=key[1])
                        preview_key = key
                    canvas = assistant_preview(preview_image, status+f" / Mic: {'Board' if args.mic_source == 'esp32' else 'Laptop'}", transcript, args.host, panel.error,
                                               size=size, details=details)
                    cv2.imshow(window, canvas)
                    key = cv2.waitKey(20) & 0xff
                    if ord("A") <= key <= ord("Z"):
                        key += 32
                    if key == ord("q"):
                        break
                    if key == ord("a"):
                        commands.put(("keyboard_wake", "listening test"))
                    if key in (ord("w"), ord("t")):
                        commands.put(("keyboard", "weather" if key == ord("w") else "show me my tasks for today"))
                    if key == ord("r"):
                        panel.set_frame(current, listening=current_kind in ("listening", "listening_demo"))
                    if key == ord("d"):
                        details = not details
                    if key == ord("h"):
                        panel.mirror_x = not panel.mirror_x
                        panel.set_frame(current, listening=current_kind in ("listening", "listening_demo"))
                        print(f"LCD horizontal mirror: {'ON' if panel.mirror_x else 'OFF'}", flush=True)
                    if key == ord("f"):
                        fullscreen = not fullscreen
                        cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN,
                                              cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
                else:
                    stop.wait(.02)
                if args.seconds and time.monotonic()-start >= args.seconds:
                    break
    finally:
        stop.set()
        panel.stop.set()
        panel.changed.set()
        panel.thread.join(timeout=3)
        if voice_thread:
            voice_thread.join(timeout=1)
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
