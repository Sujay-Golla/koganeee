"""A small daily task list with strict voice commands and atomic local storage."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import tempfile

SHOW_TASKS = ("show me my tasks for today", "show my tasks for today", "show me my tasks",
              "show my tasks", "show my tasks today", "show me my tasks today",
              "show my to do list", "show me my to do list", "my tasks", "tasks")
NUMBER_WORDS = {word: i for i, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
for tens, value in (("twenty", 20), ("thirty", 30), ("forty", 40), ("fifty", 50),
                    ("sixty", 60), ("seventy", 70), ("eighty", 80), ("ninety", 90)):
    NUMBER_WORDS[tens] = value
    for unit, number in list(NUMBER_WORDS.items()):
        if 1 <= number <= 9:
            NUMBER_WORDS[tens+" "+unit] = value+number
NUMBER_PATTERN = r"(?:[0-9]{1,4}|"+"|".join(sorted(NUMBER_WORDS, key=len, reverse=True))+r")"


@dataclass(frozen=True)
class TaskCommand:
    action: str
    task_id: int | None = None
    title: str = ""


def clean_command(text):
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", text.lower()).split())


def task_number(text):
    if text.isdigit():
        value = int(text)
    else:
        value = NUMBER_WORDS.get(text, 0)
    return value if 1 <= value <= 9999 else None


def parse_task_command(text):
    text = clean_command(text)
    if text in SHOW_TASKS:
        return TaskCommand("show")
    fixed = {"next page": "next", "previous page": "previous", "go back a page": "previous",
             "undo": "undo", "undo last change": "undo", "undo that": "undo"}
    if text in fixed:
        return TaskCommand(fixed[text])
    add = re.fullmatch(r"new task (.+)", text)
    if add and add[1] != "[unk]" and "unk" not in add[1].split():
        return TaskCommand("add", title=add[1])
    match = re.fullmatch(r"(complete|finish|delete|remove|mark) task (?:number )?("+NUMBER_PATTERN+r")(?: (?:as )?(done|complete))?", text)
    if match and (number := task_number(match[2])):
        if match[1] == "mark" and not match[3]:
            return None
        if match[1] in ("delete", "remove") and match[3]:
            return None
        return TaskCommand("delete" if match[1] in ("delete", "remove") else "complete", number)
    rename = re.fullmatch(r"(?:rename|change) task (?:number )?("+NUMBER_PATTERN+r") (?:to )?(.+)", text)
    if rename and (number := task_number(rename[1])) and "unk" not in rename[2].split():
        return TaskCommand("rename", number, rename[2])
    return None


class TaskStore:
    """Keep separate dates, stable task numbers and the last ten edits for undo."""

    def __init__(self, path, *, today=date.today):
        self.path, self.today = Path(path), today
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self._validate(self.data)
        else:
            self.data = dict(type="kogane.tasks", version=1, days={})

    @staticmethod
    def _validate(data):
        def require(condition):
            if not condition:
                raise ValueError("Invalid task data")
        try:
            require(data["type"] == "kogane.tasks" and data["version"] == 1)
            require(isinstance(data["days"], dict))
            for day, state in data["days"].items():
                date.fromisoformat(day)
                require(isinstance(state["undo"], list) and len(state["undo"]) <= 10)
                for snapshot in [state, *state["undo"]]:
                    require(type(snapshot["next_id"]) is int and 0 < snapshot["next_id"] <= 10000)
                    ids = []
                    require(isinstance(snapshot["items"], list) and len(snapshot["items"]) <= 30)
                    for item in snapshot["items"]:
                        require(type(item["id"]) is int and 0 < item["id"] < snapshot["next_id"])
                        require(isinstance(item["text"], str) and 0 < len(item["text"]) <= 120)
                        require(type(item["done"]) is bool)
                        ids.append(item["id"])
                    require(len(ids) == len(set(ids)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Task file is invalid; keep it for recovery instead of overwriting it") from exc

    def _state(self, data=None):
        return (data if data is not None else self.data)["days"].get(
            self.today().isoformat(), dict(next_id=1, items=[], undo=[]))

    def items(self):
        return deepcopy(self._state()["items"])

    def _save(self, candidate):
        self._validate(candidate)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".tasks-", suffix=".tmp", delete=False) as output:
                pending = Path(output.name)
                json.dump(candidate, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(pending, self.path)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
        self.data = candidate

    def execute(self, command):
        """Return a short notice, spoken reply and optional task to bring into view."""
        if command.action == "show":
            items = self.items()
            left = sum(not item["done"] for item in items)
            return "", (f"You have {len(items)} tasks today, with {left} remaining." if items else
                         "Your task list is empty. Say new task, followed by your task."), None
        candidate = deepcopy(self.data)
        state = candidate["days"].setdefault(self.today().isoformat(), dict(next_id=1, items=[], undo=[]))
        if command.action == "undo":
            if not state["undo"]:
                raise ValueError("Nothing to undo")
            old = state["undo"].pop()
            state.update(old)
            self._save(candidate)
            return "Change undone", "Undid the last task change.", None
        if command.action not in ("add", "complete", "delete", "rename"):
            raise ValueError("Unknown task command")
        snapshot = dict(next_id=state["next_id"], items=deepcopy(state["items"]))
        title = " ".join(command.title.split())
        if command.action in ("add", "rename"):
            if not title or len(title) > 120:
                raise ValueError("Use a task title of 1 to 120 characters")
            title = title[0].upper()+title[1:]
        if command.action == "add":
            if len(state["items"]) >= 30 or state["next_id"] > 9999:
                raise ValueError("Today's list is full")
            item = dict(id=state["next_id"], text=title, done=False)
            state["next_id"] += 1
            state["items"].append(item)
            notice, speech = f"Added task {item['id']}", f"Added task {item['id']}: {title}."
        else:
            item = next((item for item in state["items"] if item["id"] == command.task_id), None)
            if item is None:
                raise ValueError(f"Task {command.task_id} was not found")
            if command.action == "complete":
                if item["done"]:
                    return f"Task {item['id']} already done", f"Task {item['id']} is already done.", item["id"]
                item["done"] = True
                notice, speech = f"Task {item['id']} done", f"Task {item['id']} marked done."
            elif command.action == "rename":
                item["text"] = title
                notice, speech = f"Renamed task {item['id']}", f"Task {item['id']} is now: {title}."
            else:
                state["items"].remove(item)
                notice, speech = f"Deleted task {item['id']}", f"Deleted task {item['id']}."
        state["undo"] = [*state["undo"], snapshot][-10:]
        self._save(candidate)
        return notice, speech, item["id"]


class TaskBoard:
    def __init__(self, store):
        self.store, self.page, self.notice, self.revision = store, 0, "", 0

    def handle(self, words):
        command = parse_task_command(words)
        if command is None:
            raise ValueError("Say New task followed by the task, or Show my tasks")
        pages = max(1, (len(self.store.items())+2)//3)
        if command.action in ("next", "previous"):
            self.page = max(0, min(self.page+(1 if command.action == "next" else -1), pages-1))
            self.notice = ""
            speech = f"Page {self.page+1} of {pages}."
        else:
            self.notice, speech, focus = self.store.execute(command)
            items = self.store.items()
            if command.action == "show":
                self.page = 0
            elif focus is not None:
                self.page = next((i//3 for i, item in enumerate(items) if item["id"] == focus), self.page)
            self.page = max(0, min(self.page, max(0, (len(items)-1)//3)))
        self.revision += 1
        return speech
