"""Bounded wake sessions, live listening transitions, and display-only wire output."""
import json
import threading
from types import SimpleNamespace
import pytest

from kogane_base.net.sink import ListSink
from kogane_base.protocol import MsgType, unpack_screen_header, unpack_screen_text, unpack_screen_tile, SF_F_STATUS
from kogane_base.screen.sender import ScreenSender
from kogane_base.tools import demo_assistant as demo


def test_a_wake_is_required_for_each_command_and_whole_names_are_matched():
    session = demo.WakeSession(timeout_s=12)
    assert session.accept("show me my tasks for today", .99, 10) == []
    assert session.accept("something kogan", .99, 10) == []
    assert session.accept("koganomics", .99, 10) == []
    assert session.accept("coggan", .99, 10) == [("wake", "coggan")]
    assert session.accept("show me my tasks for today", .99, 11) == [("voice", "show me my tasks for today")]
    assert session.accept("weather", .99, 12) == []
    assert session.accept("ko gane show me the weather today", .99, 13) == [
        ("wake", "ko gane show me the weather today"), ("voice", "show me the weather today")]


def test_timeout_low_confidence_and_unrelated_commands_do_not_execute():
    session = demo.WakeSession(timeout_s=5)
    assert not session.accept("cogan", .4, 10)
    session.accept("cogan", .9, 10)
    assert not session.accept("arm", .99, 11)
    assert not session.accept("weather", .4, 12)
    assert session.accept("weather", .99, 15) == [("timeout", "")]
    assert not session.tick(16)
    session.accept("kogan", .9, 17)
    session.reset()  # playback resets microphone state
    assert not session.accept("tasks", .9, 18)


def test_personal_threshold_changes_only_the_observed_name_spelling(tmp_path):
    path = tmp_path/"wake.json"
    path.write_text(json.dumps(dict(type="kogane.wake_profile", version=1, aliases=["kogan"],
                                    min_confidence={"kogan": .30})))
    aliases, thresholds = demo.load_wake_profile(path)
    session = demo.WakeSession((*demo.WAKE_ALIASES, *aliases), thresholds=thresholds)
    assert not session.accept("what", .99, 10)
    assert not session.accept("cogan", .4, 10)
    assert not session.accept("kogan", .29, 10)
    assert session.accept("kogan", .330674, 11) == [("wake", "kogan")]
    assert session.accept("show me my tasks for today", .9, 12) == [("voice", "show me my tasks for today")]
    path.write_text(json.dumps(dict(type="kogane.wake_profile", version=1, aliases=["kogan"],
                                    min_confidence={"kogan": .01})))
    with pytest.raises(ValueError, match="confidence"):
        demo.load_wake_profile(path)


def test_grammar_uses_real_lexicon_entries_and_keeps_bare_commands_for_rejection():
    model = SimpleNamespace(vosk_model_find_word=lambda word: -1 if word == "kogane" else 1)
    grammar = json.loads(demo.recognition_grammar(model))
    assert "kogane" not in grammar and "cogan" in grammar
    assert "cogan show me my tasks for today" in grammar and "show me my tasks for today" in grammar
    assert "show me a picture" not in grammar
    assert "[unk]" in grammar
    repeated = json.loads(demo.recognition_grammar(model, (*demo.WAKE_ALIASES, "kogan")))
    assert repeated.count("kogan") == 1


@pytest.mark.parametrize("rotation,mirror_x", [(0, False), (180, False), (0, True), (180, True)])
def test_listening_goes_as_fast_text_then_paced_image_and_releases_display(monkeypatch, rotation, mirror_x):
    from kogane_base.net import sink
    panel = demo.PanelOutput("127.0.0.1", 5005, rotation=rotation, mirror_x=mirror_x)

    class Transport(ListSink):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send(self, msg_type, payload):
            super().send(msg_type, payload)
            if len(self.frames) >= (144 if rotation or mirror_x else 121):
                panel.stop.set()
                panel.changed.set()

    raw = Transport()
    monkeypatch.setattr(sink, "SocketSink", lambda *args: raw)
    monkeypatch.setattr(demo, "ScreenSender", lambda transport, **kw: ScreenSender(transport, strip_delay_s=0))
    panel.set_frame(demo.card("listening"), listening=True)
    panel._run()
    assert panel.error == "" and panel.sent_revision == 1
    assert all(msg_type == int(MsgType.SCREEN_FRAME) for msg_type, _ in raw.frames)
    if rotation or mirror_x:
        first = unpack_screen_tile(raw.frames[0][1])
        assert (first.x, first.y, first.w, first.h) == (0, 96, 320, 2)
        assert first.pixels == panel.pixels[96*640:98*640]
    else:
        first = unpack_screen_text(raw.frames[0][1])
        assert first.text == "LISTENING..." and first.row == 3
    assert unpack_screen_header(raw.frames[-1][1]).flags & SF_F_STATUS


def test_two_axis_inversion_is_corrected_in_transmission_without_changing_preview():
    import numpy as np
    from PIL import Image
    image = Image.new("RGB", (320, 240), "black")
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((319, 0), (0, 0, 255))
    image.putpixel((319, 239), (0, 255, 0))
    panel = demo.PanelOutput(None, 5005, rotation=180)
    panel.set_frame(image)
    pixels = np.frombuffer(panel.pixels, dtype="<u2").reshape(240, 320)
    assert pixels[0, 0] == 0x07e0  # original bottom right -> top left
    assert pixels[239, 319] == 0xf800
    assert pixels[239, 0] == 0x001f
    assert image.getpixel((0, 0)) == (255, 0, 0)
    panel = demo.PanelOutput(None, 5005, rotation=180, mirror_x=True)
    panel.set_frame(image)
    pixels = np.frombuffer(panel.pixels, dtype="<u2").reshape(240, 320)
    assert pixels[0, 319] == 0x07e0  # additional horizontal mirror after rotation
    assert pixels[239, 0] == 0xf800
    assert pixels[239, 319] == 0x001f


@pytest.mark.parametrize("source", ["voice", "keyboard"])
def test_headless_controller_shows_listening_before_answer_and_logs_source(tmp_path, monkeypatch, source):
    panels = []

    class Panel:
        def __init__(self, host, port, **kwargs):
            self.stop, self.changed = threading.Event(), threading.Event()
            self.error, self.states = "", []
            self.thread = SimpleNamespace(start=lambda: None, join=lambda **kw: None)
            panels.append(self)

        def set_frame(self, image, *, listening=False):
            self.states.append((image, listening))

    def microphone(model, commands, paused, stop, *args):
        wake = "wake" if source == "voice" else "keyboard_wake"
        for event in [("ready", "ready"), (wake, "cogan"), (source, "show me my tasks for today")]:
            commands.put(event)

    monkeypatch.setattr(demo, "PanelOutput", Panel)
    monkeypatch.setattr(demo, "voice_worker", microphone)
    monkeypatch.setattr(demo, "BASE", tmp_path)
    assert demo.main(["--host", "127.0.0.1", "--headless", "--mute", "--seconds", "2.1"]) == 0
    states = panels[0].states
    assert [listening for _, listening in states] == [False, False, True, False]
    assert states[-1][0].tobytes() == demo.card("tasks", keyboard=source == "keyboard").tobytes()
    events = [json.loads(line) for line in (tmp_path/"outputs/assistant_events.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "wake"
    assert events[1]["intent"] == "tasks" and events[1]["input"] == source


def test_headless_voice_add_updates_saved_tasks_and_the_display(tmp_path, monkeypatch):
    from kogane_base.tools.task_list import TaskStore
    frames = []
    class Panel:
        def __init__(self, *args, **kwargs):
            self.stop, self.changed = threading.Event(), threading.Event()
            self.thread = SimpleNamespace(start=lambda: None, join=lambda **kw: None)
            self.error = ''
        def set_frame(self, image, **kwargs):
            frames.append(image)
    def microphone(model, commands, *args):
        for event in [('ready', 'ready'), ('wake', 'kogan'), ('voice', 'new task buy groceries')]:
            commands.put(event)
    monkeypatch.setattr(demo, 'PanelOutput', Panel)
    monkeypatch.setattr(demo, 'voice_worker', microphone)
    monkeypatch.setattr(demo, 'BASE', tmp_path)
    assert demo.main(['--headless', '--mute', '--seconds', '2.1']) == 0
    items = TaskStore(tmp_path/'data/tasks.json').items()
    assert items == [dict(id=1, text='Buy groceries', done=False)]
    assert frames[-1].tobytes() == demo.card('tasks', task_items=items).tobytes()


def test_show_then_follow_up_new_task_is_saved_and_shows_active_listening(tmp_path, monkeypatch):
    import time
    from kogane_base.tools.task_list import TaskStore
    frames = []
    class Panel:
        def __init__(self, *args, **kwargs):
            self.stop, self.changed = threading.Event(), threading.Event()
            self.thread = SimpleNamespace(start=lambda: None, join=lambda **kw: None)
            self.error = ''
        def set_frame(self, image, **kwargs):
            frames.append(image)
    def microphone(model, commands, paused, stop, *args):
        task_mode, rearm = args[5:7]
        for event in [('ready', 'ready'), ('wake', 'kogan'), ('voice', 'show me my tasks for today')]:
            commands.put(event)
        sent = False
        while not stop.is_set():
            if rearm.is_set() and not paused.is_set():
                rearm.clear()
                assert task_mode.is_set()
                commands.put(('task_ready', 'Listening for task commands'))
                if not sent:
                    commands.put(('voice', 'new task buy groceries'))
                    sent = True
            time.sleep(.005)
    monkeypatch.setattr(demo, 'PanelOutput', Panel)
    monkeypatch.setattr(demo, 'voice_worker', microphone)
    monkeypatch.setattr(demo, 'BASE', tmp_path)
    assert demo.main(['--headless', '--mute', '--seconds', '2.5']) == 0
    items = TaskStore(tmp_path/'data/tasks.json').items()
    assert items == [dict(id=1, text='Buy groceries', done=False)]
    assert frames[-1].tobytes() == demo.card('tasks', task_items=items, task_active=True).tobytes()
