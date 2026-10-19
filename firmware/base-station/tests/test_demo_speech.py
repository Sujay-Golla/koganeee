"""Streaming microphone conditioning and separate wake-name recognition."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from kogane_base.tools.demo_assistant import SpeechConditioner, SpeechDecoder


def test_filter_is_independent_of_stream_chunk_boundaries_and_removes_dc():
    t = np.arange(32000)/16000
    samples = np.rint(400+900*np.sin(2*np.pi*1000*t)).astype('<i2')
    whole = SpeechConditioner().process(samples.tobytes())
    live = SpeechConditioner()
    parts = b''.join(live.process(samples[n:n+1600].tobytes()) for n in range(0, len(samples), 1600))
    assert parts == whole
    output = np.frombuffer(whole, '<i2')[1000:].astype(float)
    assert abs(output.mean()) < 2
    assert np.sqrt(np.mean(output**2)) > 2400
    dc = SpeechConditioner().process(np.full(2000, 400, '<i2').tobytes())
    assert np.max(np.abs(np.frombuffer(dc, '<i2'))) == 0


def test_filter_clips_without_wrapping_and_reset_clears_history():
    f = SpeechConditioner(12)
    data = np.tile(np.array([30000, -30000], '<i2'), 1000).tobytes()
    result = np.frombuffer(f.process(data), '<i2')
    assert result.max() == 32767 and result.min() == -32768
    f.reset()
    assert f.process(data) == SpeechConditioner(12).process(data)
    for value in (0, 13, float('nan')):
        with pytest.raises(ValueError):
            SpeechConditioner(value)


def decoder():
    instances = []

    class Recognizer:
        def __init__(self, model, rate, grammar=None):
            self.grammar, self.pending = json.loads(grammar) if grammar else None, None
            instances.append(self)

        def SetWords(self, value):
            pass

        def AcceptWaveform(self, data):
            return self.pending is not None

        def Result(self):
            result, self.pending = self.pending, None
            return json.dumps(result)

        def Reset(self):
            self.pending = None

    model = SimpleNamespace(vosk_model_find_word=lambda w: -1 if w == 'kogane' else 1)
    d = SpeechDecoder(model, thresholds={'kogan': .3}, recognizer_factory=Recognizer)
    return d, instances


def result(text, conf=.9):
    return dict(text=text, result=[dict(word=w, conf=conf) for w in text.split()])


def test_separate_name_decoder_opens_once_then_accepts_one_command():
    d, (joint, names, free) = decoder()
    assert 'weather' not in names.grammar and '[unk]' in names.grammar
    joint.pending, names.pending = result('what'), result('kogan', .38)
    assert d.feed(b'\0\0'*1600, 1) == [('wake', 'kogan')]
    joint.pending = result('kogan', .4)
    names.pending = result('kogan', .4)
    assert d.feed(b'\0\0'*1600, 2) == []
    free.pending, names.pending = result('show me my tasks for today'), result('kogan', .4)
    assert d.feed(b'\0\0'*1600, 3) == [('voice', 'show me my tasks for today')]
    joint.pending = result('weather')
    assert d.feed(b'\0\0'*1600, 4) == []


def test_delayed_joint_combined_phrase_keeps_one_wake_and_the_command():
    d, (joint, names, free) = decoder()
    names.pending = result('kogan', .4)
    assert d.feed(b'\0\0'*1600, 1) == [('wake', 'kogan')]
    free.pending = result('kogan show me the weather today')
    assert d.feed(b'\0\0'*1600, 2) == [('voice', 'show me the weather today')]


def test_task_titles_use_free_speech_and_fixed_grammar_cannot_replace_them():
    d, (joint, names, free) = decoder()
    free.pending = result('new task buy groceries')
    assert d.feed(b'\0\0'*1600, 1) == []  # No wake, no edit.
    names.pending = result('kogan', .4)
    assert d.feed(b'\0\0'*1600, 2) == [('wake', 'kogan')]
    free.pending, joint.pending = result('new task check weather [unk]'), result('weather')
    assert d.feed(b'\0\0'*1600, 3) == []
    free.pending, joint.pending = result('new task buy groceries'), result('weather')
    assert d.feed(b'\0\0'*1600, 4) == [('voice', 'new task buy groceries')]
    assert not d.session.until


def test_fixed_view_and_undo_fallback_but_never_guessed_task_edits():
    d, (joint, names, free) = decoder()
    names.pending = result('kogan', .4)
    d.feed(b'\0\0'*1600, 1)
    free.pending, joint.pending = result('shall we my tasks for today'), result('show me my tasks for today')
    assert d.feed(b'\0\0'*1600, 2) == [('voice', 'show me my tasks for today')]
    names.pending = result('kogan', .4)
    d.feed(b'\0\0'*1600, 3)
    joint.pending = result('complete task one')
    assert d.feed(b'\0\0'*1600, 4) == []
    free.pending, joint.pending = result('i do less change'), result('undo last change')
    assert d.feed(b'\0\0'*1600, 5) == [('voice', 'undo last change')]


@pytest.mark.parametrize('text,confidence', [('what', 1), ('gane', 1), ('kogan [unk]', 1),
                                          ('[unk] kogan', 1), ('kogan', .29)])
def test_common_words_partial_names_embedded_names_and_low_confidence_rejected(text, confidence):
    d, (joint, names, free) = decoder()
    names.pending = result(text, confidence)
    assert d.feed(b'\0\0'*1600, 1) == []


def test_combined_command_and_timeout_still_work():
    d, (joint, names, free) = decoder()
    joint.pending = result('coggan show me the weather today')
    assert d.feed(b'\0\0'*1600, 1) == [('wake', 'coggan show me the weather today'),
                                          ('voice', 'show me the weather today')]
    names.pending = result('kogan', .4)
    assert d.feed(b'\0\0'*1600, 2) == [('wake', 'kogan')]
    assert d.tick(14) == [('timeout', '')]
    names.pending = result('kogan', .4)
    d.reset()
    assert d.feed(b'\0\0'*1600, 15) == []


def test_task_follow_up_accepts_new_task_after_show_without_another_wake():
    d, (joint, names, free) = decoder()
    names.pending = result('kogan', .4)
    d.feed(b'\0\0'*1600, 1)
    free.pending = result('show me my tasks for today')
    assert d.feed(b'\0\0'*1600, 2) == [('voice', 'show me my tasks for today')]
    d.reset()  # Playback pauses recognition.
    d.begin_tasks(3)
    free.pending = result('new task buy groceries', .96)
    assert d.feed(b'\0\0'*1600, 4) == [('voice', 'new task buy groceries')]
    assert not d.session.until and not d.task_until


def test_task_follow_up_is_bounded_task_only_and_can_stop():
    d, (joint, names, free) = decoder()
    d.begin_tasks(1, 5)
    free.pending = result('weather')
    assert d.feed(b'\0\0'*1600, 2) == []
    assert d.rejection == ('wake_required', 'weather')
    free.pending = result('new task buy groceries', .4)
    assert d.feed(b'\0\0'*1600, 3) == []
    assert d.rejection == ('low_confidence', 'new task buy groceries')
    free.pending = result('new task buy groceries', .96)
    assert d.feed(b'\0\0'*1600, 7) == [('task_timeout', '')]
    assert d.rejection == ('wake_required', 'new task buy groceries')
    d.begin_tasks(8)
    free.pending = result('stop listening')
    assert d.feed(b'\0\0'*1600, 9) == [('voice', 'stop listening')]
    free.pending = result('new task buy groceries')
    assert d.feed(b'\0\0'*1600, 10) == []
