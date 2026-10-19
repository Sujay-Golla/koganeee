"""Voice edits persist, target stable IDs, and cannot silently destroy saved data."""
from datetime import date
import json

import pytest

from kogane_base.tools.task_list import TaskStore, TaskBoard, TaskCommand, parse_task_command
from kogane_base.tools.demo_assistant import WakeSession


@pytest.mark.parametrize('words,action,number,title', [
    ('Show me my tasks for today', 'show', None, ''),
    ('new task buy groceries', 'add', None, 'buy groceries'),
    ('new task charge the battery', 'add', None, 'charge the battery'),
    ('complete task one', 'complete', 1, ''),
    ('mark task 2 as done', 'complete', 2, ''),
    ('delete task twenty one', 'delete', 21, ''),
    ('rename task two to buy apples', 'rename', 2, 'buy apples'),
    ('next page', 'next', None, ''),
    ('undo last change', 'undo', None, ''),
])
def test_voice_commands(words, action, number, title):
    assert parse_task_command(words) == TaskCommand(action, number, title)


@pytest.mark.parametrize('words', ['new task', 'new task [unk]', 'complete task zero',
                                  'delete all tasks', 'a conversation about tasks',
                                  'please arm the drone', 'mark task one', 'show me a picture'])
def test_ambiguous_or_unsupported_commands_are_not_edits(words):
    assert parse_task_command(words) is None


def test_changes_survive_restart_keep_ids_and_undo(tmp_path):
    path = tmp_path/'tasks.json'
    board = TaskBoard(TaskStore(path))
    board.handle('new task buy groceries')
    board.handle('new task charge battery')
    board.handle('complete task one')
    board.handle('rename task two to charge the camera')
    assert TaskStore(path).items() == [dict(id=1, text='Buy groceries', done=True),
                                       dict(id=2, text='Charge the camera', done=False)]
    board.handle('delete task one')
    assert board.store.items()[0]['id'] == 2
    board.handle('undo last change')
    assert board.store.items()[0]['id'] == 1 and board.store.items()[0]['done']
    board.handle('undo last change')
    assert board.store.items()[1]['text'] == 'Charge battery'
    before = path.read_bytes()
    with pytest.raises(ValueError, match='not found'):
        board.handle('delete task nine')
    assert path.read_bytes() == before


def test_day_rollover_preserves_old_date_and_paging(tmp_path):
    current = [date(2026, 10, 18)]
    store = TaskStore(tmp_path/'tasks.json', today=lambda: current[0])
    board = TaskBoard(store)
    for n in range(5):
        board.handle(f'new task item {n}')
    assert board.page == 1
    board.handle('show me my tasks for today')
    assert board.page == 0
    board.handle('next page')
    assert board.page == 1
    board.handle('next page')
    assert board.page == 1
    current[0] = date(2026, 10, 19)
    assert store.items() == []
    board.handle('new task new day')
    assert len(store.data['days']['2026-10-18']['items']) == 5
    assert store.items()[0]['id'] == 1


def test_failed_save_does_not_change_memory_or_disk(tmp_path, monkeypatch):
    import kogane_base.tools.task_list as tasks
    store = TaskStore(tmp_path/'tasks.json')
    store.execute(TaskCommand('add', title='First task'))
    before, memory = store.path.read_bytes(), store.items()
    def fail(*args):
        raise OSError('disk failure')
    monkeypatch.setattr(tasks.os, 'replace', fail)
    with pytest.raises(OSError):
        store.execute(TaskCommand('delete', 1))
    assert store.path.read_bytes() == before and store.items() == memory
    assert not list(tmp_path.glob('.tasks-*.tmp'))


def test_invalid_file_is_preserved_and_too_long_title_does_not_write(tmp_path):
    path = tmp_path/'tasks.json'
    path.write_text(json.dumps(dict(type='kogane.tasks', version=1, days={'2026-10-18': {}})))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='invalid'):
        TaskStore(path)
    assert path.read_bytes() == before
    new = TaskStore(tmp_path/'new.json')
    with pytest.raises(ValueError):
        new.execute(TaskCommand('add', title='x'*121))
    assert not new.path.exists()


def test_voice_edit_needs_wake_and_consumes_it():
    session = WakeSession()
    assert session.accept('new task buy groceries', .99, 1) == []
    assert session.accept('kogan', .99, 2) == [('wake', 'kogan')]
    assert session.accept('new task buy groceries', .99, 3) == [('voice', 'new task buy groceries')]
    assert session.accept('delete task one', .99, 4) == []
    session.accept('kogan', .99, 5)
    assert session.accept('complete task 2', .99, 6) == [('voice', 'complete task 2')]
