# Kogane: voice-editable tasks for today

Updated 2026-10-18. The task list replaces the picture command. Weather remains
available with [real weather from Open-Meteo](WEATHER_DEMO.md). Voice and tasks
run locally with the existing free Vosk and Windows speech setup. Weather needs
internet; no account, subscription, new model download or ESP32 flash is needed.

## Start on the laptop now

Close the old assistant with **Q**, then run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

Input 3 is the currently working laptop Realtek MME microphone. Keep that selection
unless device numbering changes. F toggles fullscreen; D shows optional details.
The card uses the whole viewing area, with three task rows per page.

The selected [Natural voice](VOICE_STYLE.md) is now the default for task and
weather replies. Its free local model is already installed; no voice flag is
needed. Other styles remain available through `--speech-style`.

The compact layout shows **Today**, large task rows and one status line. There
are no repeated instructions, permanent success messages or remaining-count
labels. Page numbers appear only for multiple pages. Completed tasks keep their
check and strike-through; actual errors still show a short notice.

**Say Kogane and wait for Listening to open the list or start a task command.**
After each task reply, the list's footer shows **Listening** for 30 seconds.
During that window, say the next task command directly, without another wake word.
Speak the complete command as one utterance, including the task title when adding
or renaming. Wait until the spoken reply finishes and **Listening** appears.

Each task reply renews that window. After 30 seconds of inactivity, the footer
changes to **Say Kogane**. Say **Stop listening** to end task editing immediately.
Weather still needs Kogane. `--task-session-seconds 60` gives a longer task window.

| Say after Kogane | Result |
| --- | --- |
| **Show me my tasks for today** | Show today's saved list, starting at page one |
| **New task buy groceries** | Add the title “Buy groceries” and show its number |
| **New task charge the battery** | Add another task |
| **Complete task one** | Check off task 1 |
| **Rename task number one to charge the camera** | Change task 1's title |
| **Delete task two** | Remove task 2 |
| **Undo last change** | Undo the most recent task edit |
| **Next page** / **Previous page** | Browse a longer list |
| **Stop listening** | End the task follow-up window |
| **Show me the weather today** | Fetch Toronto's current conditions and today's high/low |

Use **task number one** when renaming: it decoded more reliably in the speech
check than **task one to**, which the small English model sometimes hears as
“task want to.” Use short, ordinary task titles first. General speech recognition
can still mishear a title; the displayed title and spoken reply let you check it.
Rename it or undo the edit if needed. The app does not invent missing titles.

Task numbers stay fixed when you complete or delete a task. Use the number shown
on screen, rather than assuming row two is always task 2. Completed tasks remain
visible with a check and strike-through. Adding or editing a task brings its page
into view. An empty list starts empty; no example tasks are inserted automatically.

## A short recording sequence

1. Kogane → **Show me my tasks for today**.
2. Wait for the reply and **Listening** in the footer → **New task charge the battery**.
3. Wait for the reply → **New task record the demo video**.
4. Wait for the reply → **Complete task one**, using the actual task number if your list
   already contained tasks.
5. Say **Stop listening**, then hold the checked list on screen for a few seconds.

The list is real, editable data. Keep the wake and Listening transitions in the
clip. T is a keyboard-labelled list preview, W is keyboard-labelled weather,
and A is a keyboard-labelled listening rehearsal. Keyboard tests should not be
presented as voice recognition. The former picture command and P shortcut are gone.

## Physical FC screen in the next powered session

Use the same command with the current ESP32 address and orientation settings:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3 --host 10.0.0.47 --lcd-rotation 180 --lcd-mirror-x
```

No battery is needed for laptop rehearsal. Physical LCD reception/layout still
needs a powered check. The tool sends display packets only.

## Saving and dates

- Tasks save immediately to `firmware\base-station\data\tasks.json`, after each
  successful edit. The app confirms the edit after saving. Back up this file if
  the list matters to you; it is private and ignored by Git.
- Each laptop calendar date has its own list. A new date starts empty; previous
  dates remain in the file. Unfinished tasks are not automatically carried over.
- The list survives closing and reopening the assistant. Undo history survives
  too, for the last ten changes on that date.
- Up to 30 tasks per date; titles up to 120 characters. Long titles wrap to two
  lines and may be shortened on the LCD. The saved title remains complete.
- `--tasks-file "C:\path\tasks.json"` selects a different local file, useful for
  a separate rehearsal list. Close other assistant instances before editing.
- Invalid saved data is not overwritten. A save failure leaves the previous
  saved list and in-memory list intact and shows a failure notice.

## Verification

63 focused checks passed: command parsing, wake gating, general title decoding,
fixed viewing/undo fallback, atomic persistence/restart, failed-save recovery,
stable IDs, edits/undo, day separation, paging, headless voice-to-card persistence,
and existing display transport/orientation behavior. The regression case opens
the list, rearms the microphone after its reply, accepts a new task without a
second wake and verifies both saved data and the active-listening card. Inactive
recognized commands now print `Not executed (wake_required)` and show a prompt;
the `Heard` line alone does not mean a command ran.

Actual offline Vosk replay of generated Windows speech passed the table's viewing,
add, complete, explicit-number rename, delete, undo and paging commands, plus
weather. Commands were also rejected without an initial wake/task session. Unrelated speech
did not execute a command after a wake. A full add/complete/rename/delete/undo
sequence preserved the expected task state. These are synthesized-speech checks.
The follow-up fix also passed actual Vosk replay of wake → show tasks → new task,
then saving and reopening the list. Your live voice and physical LCD still need
verification. No user microphone, camera or FC was opened for the automated checks.
