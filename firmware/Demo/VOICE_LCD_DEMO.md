# Kogane wake word → listening LCD → answer card

**Microphone choice:** the demo video keeps laptop input (`--device 3`).
[BOARD_MIC_TEST.md](BOARD_MIC_TEST.md) provides a separate stationary onboard-mic
recording and command test with `--mic-source esp32`. Laptop remains the default.

**Voice options:** [VOICE_STYLE.md](VOICE_STYLE.md) has free offline bright,
mascot and electronic candidates inspired by the Japanese character's general
delivery. English replies are retained. The user selected **Natural**, now the
default (`mascot-natural`) for weather and task replies. Restart with `--device 3`;
no voice flag is needed. Other styles remain available as explicit overrides.

**Real weather, 2026-10-18:** [WEATHER_DEMO.md](WEATHER_DEMO.md) replaces the fixed
weather response with Open-Meteo current conditions and today's high/low for
Toronto. No key or account is required for this personal demo. The laptop needs
internet; failed requests show Weather unavailable. Older preset descriptions
below are historical.

**Current second command: tasks.** [TASKS_DEMO.md](TASKS_DEMO.md) replaces the
picture demonstration with a saved, voice-editable daily task list. Say Kogane,
wait for Listening, then **Show me my tasks for today**. Add, complete, rename,
delete, undo and paging commands are in that guide. Use microphone `--device 3`.
The historical picture instructions below describe the previous version.

**Task follow-ups:** after the task list's spoken reply, its footer shows
**Listening**. Task commands such as **New task buy groceries** work directly for
30 seconds, renewed after each reply. **Stop listening** ends that window. Once
the footer says **Say Kogane**, wake it again. The older one-wake-per-command
description below applies outside this new task follow-up mode.

**Current compact layout:** Today + checklist + a quiet Listening/Say Kogane
footer. Task titles are 24 px on the LCD. Repeated instructions, success notices,
counts and single-page counters have been removed. Ready/listening screens also
show only their primary cue. The sidebar remains removed.

**Preparing with the FC off:** see [DEMO_RECORDING_PLAN.md](DEMO_RECORDING_PLAN.md)
for real laptop-only voice rehearsal, mapping recording now, and the short
physical-LCD recording sequence for the next battery-powered session.

## Enlarged display — 2026-10-18

The assistant now devotes its window to the card, with no sidebar, slogan,
diagnostic columns or permanent shortcut bar. **F** maximizes it fullscreen.
**D** toggles optional details in a temporary bottom panel. Transport failures
still show a short error notice; full details remain in the terminal.

The physical 320x240 LCD cards also use much larger type: prominent Kogane and
Listening headings, a prominent temperature and compact forecast, and large task
rows. Keyboard tests remain labelled. Text fits
within the available bounds; the laptop redraws the same design at native pixel
density rather than enlarging the LCD bitmap. A widescreen laptop preserves the
LCD's 4:3 proportions at the largest fitting size. No sidebar occupies that space.

Restart with the confirmed laptop microphone:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

For the physical display later, add `--host 10.0.0.47 --lcd-rotation 180
--lcd-mirror-x`, using the current ESP32 IP. No firmware flash is needed. Q closes
the old process before restarting. The microphone, wake logic and LCD orientation
options are unchanged by the layout update. 22 existing voice/card/transport
checks passed, and rendered LCD/native-density previews were visually inspected.
The physical LCD layout still needs the next battery-powered check.

## Current microphone selection — 2026-10-18

User requires free tools only. Read-only device inspection found Windows currently
defaults to input 1, **Microphone (2- USB Audio)**, rather than the laptop array.
Input **3**, **Microphone Array (Realtek(R) Audio)** through MME, supports the demo's
16 kHz mono int16 format. Its WASAPI duplicate at index 15 does not support that
format. No microphone was opened or recorded during these checks. The default
USB device may be a webcam; its exact hardware identity has not been confirmed.

Select the laptop microphone explicitly for the next test:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

If it is still unreliable, close with Q and record using the same input:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.wake_sample --device 3 --seconds 30
```

The user confirms this selection works a lot better. Use `--device 3` with the LCD
command too. Device indices may change after USB
changes/reboot; `--list-mics` identifies the current Realtek Microphone Array MME
index. Keep the current free Vosk setup for the demo unless further tests show
a need to change engines.

The free, Apache-2.0 sherpa-onnx engine (1.13.8) and official 2025-12-20 bilingual
keyword model were installed/downloaded locally for comparison. The initial
phoneme keyword trials detected none of the names in either user recording,
so that engine has **not** replaced the live Vosk path. Existing recordings were
only processed locally. No account, API key, paid service or audio upload was used.
Resolve the selected microphone before spending more time tuning that comparison.

## Latest voice recalibration — 2026-10-18

The user's new 30-second recording produced no wake events with the old joint
name/command decoder. The demo now runs a separate, small name recognizer in
parallel with the command recognizer. Only a complete accepted name can open the
session through that fallback; `what`, `gane` and names embedded in unknown speech
are rejected. The original command recognizer retains combined wake + command
support. Duplicate endpoints from the two recognizers do not cause a second wake.

Microphone input now passes through streaming 80 Hz high-pass filtering to remove
DC offset/rumble, followed by bounded 4x gain. Both supplied recordings contained
an input offset; the earlier one also had strong low-frequency noise. No new
dependency or ESP32 firmware change is needed. `--mic-gain 1` reduces the gain
for a louder microphone; valid values are 1-12. The existing personal `kogan`
threshold remains 0.30; no common words were added as wake aliases.

Offline replay finds four exact `kogan` name matches in the first recording and
five in the latest one. These are decoder matches, not five complete interactions:
an already-open listening session ignores repeat wake names until a command or
timeout. Some repetitions are still missed. This is phrase recognition, not custom
wake-model training or speaker identification. Live reliability still needs a test.

Original WAVs and reports are preserved. New analysis is saved alongside each as
`.recalibrated.recognition.json`; it includes `wake_name_grammar` in addition to
the command grammar. The recording tool now analyzes with the same streaming
conditioning and decoder used by the live assistant.

Restart the assistant, with the FC off if desired:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant
```

Say Kogane, wait for Listening, then request weather. After the reply, repeat with
the picture command. Every interaction needs a new wake. Preserve `--device N`
if you previously selected a specific microphone. If it misses, share the new
`Heard (name)` / `Heard (joint)` terminal lines. Also try ordinary conversation
without the name to check for false activation in your actual room.

34 focused checks passed for filtering/chunk continuity, clipping/reset, wake
gating, duplicate endpoints, combined commands, timeouts, recording and display
behavior. Real Vosk replay still accepts synthesized Kogane and the combined
weather request, and rejects the available bare weather/picture and unrelated
speech clips. Silence, constant offset and generated low-frequency rumble also
produce no events. These limited negative checks do not establish a general
false-activation rate.

Updated 2026-10-17. The user confirms the FC power issue has been manually verified
and is fine. Use that verified power arrangement. No additional ESP32 flash is
needed if the working Wi-Fi/display firmware remains installed.

**Latest orientation correction:** User reports the 180-degree correction still
needs a horizontal mirror. The assistant now rotates by 180 degrees and then
mirrors horizontally by default. Restart to apply it; explicitly use
`--lcd-rotation 180 --lcd-mirror-x`. The laptop preview stays upright.
Press H in the laptop window to toggle just the horizontal mirror immediately;
the terminal prints ON/OFF. `--no-lcd-mirror-x` disables that additional mirror.
`--lcd-rotation 0 --no-lcd-mirror-x` disables both corrections if the mounting or
firmware orientation changes later. Quick listening feedback uses transformed RGB
pixels whenever a correction is active, avoiding a mismatched firmware text overlay.
This correction applies to assistant output, not the ESP32's own status screen.

## 1. Start the combined voice and LCD demo

1. Power the FC/display and let the ESP32 join your home Wi-Fi.
2. Put the laptop on the same network. Close any old assistant or base-station
   program that is sending screen updates. The mapping tool sends no screen
   packets, but you may close it to simplify the recording.
3. Open PowerShell and run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --host 10.0.0.47 --lcd-rotation 180 --lcd-mirror-x
```

10.0.0.47 is the last verified ESP32 address. If its boot log shows another address,
substitute that address. This command uses the **laptop microphone and speakers**.
It sends display packets only; no arm, flight, audio-to-drone or servo commands.

## 2. What to say and what should appear

1. Wait through **Starting up…**. When the microphone opens, the LCD should show
   **Say “Kogane”**. The laptop displays the same card and recognition status.
2. Say **Kogane** clearly, then pause. Wait for the green **Listening…** card on the
   physical LCD. A small waveform symbol and command prompts indicate readiness.
3. Say **Show me the weather today**.
4. The LCD should change to the weather card and the laptop should speak its
   answer. Weather now comes from the live service described in WEATHER_DEMO.md.
5. Say **Kogane** again and wait for **Listening…**.
6. Say **Show me a picture**. The LCD should show the preset picture and the laptop
   should answer. Use `--picture "C:\absolute\path\picture.jpg"` for your own image.
7. Press Q in the laptop window when finished. The display is released back to
   the ESP32's status screen.

Every command needs a new wake word. The listening window lasts **12 seconds**;
if no accepted command arrives, the display restores the previous answer or ready
card. Microphone recognition pauses during laptop speech and resumes afterward.
The answer card remains visible until the next interaction.

Wake-plus-command in one utterance is supported, but the two-step sequence is
easier to debug and makes the LCD listening transition clear in a video.

## 3. If something does not happen

### LCD stays on the ESP32 status screen

- Check the current ESP32 IP, home Wi-Fi and display power.
- Press A in the laptop assistant window. This triggers a **keyboard-labelled
  listening demonstration**, allowing you to check the display path separately.
- W and P send keyboard-labelled weather/picture cards. These are rehearsal
  controls, not evidence of voice recognition. R resends the current card.
- If the laptop card changes but the LCD does not, send the laptop's LCD error
  text and the ESP32's current IP. UDP has no delivery acknowledgement; the laptop
  preview alone does not confirm that the physical panel received the image.

### Kogane does not trigger Listening

- Check the terminal's `Heard: ... / confidence ...` line.
- The small English Vosk model has no literal Kogane word. The implementation
  uses existing phonetic name spellings (`kogan`, `cogan`, `coggan`, `ko gane`).
  These are pronunciation matches, not a separately trained wake-word model.
- If nothing is heard, check microphone selection and Windows microphone access:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --list-mics
```

Then rerun the main command with `--device N` using the appropriate input index.
If speech is heard but the name is consistently different, share that exact Heard
line. `--wake-alias "recognised spelling"` can add another existing English-model
spelling. Do not add a common command word such as weather as a wake alias.

### Record your pronunciation for tuning

**Your first sample has now been reviewed.** The original report decoded three
utterances as `kogan` at confidence 0.359, 0.433 and 0.331; the original 0.65 cutoff
rejected them. A local, ignored `calib\wake_pronunciation.json` now sets only that
spelling's cutoff to 0.30. Other spellings stay at 0.65, and common words such as
`what` are excluded. This profile loads automatically when the assistant starts.

Offline replay now yields three wake events instead of zero. The first decoded
utterance is still missed. Bare command and unrelated synthesized-speech checks
remain rejected; those checks do not establish a general false-wake rate. Live
recognition still needs your test. The original WAV/report were preserved; the
new results are saved beside them as `.tuned.recognition.json`.

Close the assistant with Q, then run from the base-station folder:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.wake_sample --seconds 20
```

After the 3–2–1 countdown and RECORDING message, say **Kogane** naturally 5–6
times, with about two seconds of silence between repetitions. Use your usual
microphone distance and pronunciation. The tool stops automatically, saves a
timestamped WAV under `outputs\wake_samples`, and writes a `.recognition.json`
report showing both unconstrained recognition and current wake-grammar results.
Existing recordings are never overwritten. Add `--device N` to select a microphone.

Share the printed Saved path/report, or attach the WAV. We can review those sounds
and decoded spellings to tune the phrase. Nothing is uploaded automatically and
no wake alias or speech model is automatically changed. A few samples support
diagnosis and phrase tuning; they do not train a reliable custom wake-word model
or identify the speaker. `--analyze PATH.wav` checks an existing WAV without opening
the microphone, and `--no-analysis` records only.

### Listening appears, but the command is missed

- Wait until the green Listening card appears before speaking the command.
- Use one of the two exact phrases above and speak toward the laptop microphone.
- Try `--listen-seconds 20` for a longer command window.
- If the screen has missing strips, R resends the image. Changed cards are sent
  immediately; full frames are paced to suit the ESP32 display queue, with small
  keepalives and periodic refreshes.

F toggles fullscreen for the laptop preview, with native-resolution typography.
H toggles the LCD's additional horizontal mirror.
`--mute` disables spoken responses. `--no-mic` is keyboard rehearsal only and is
labelled accordingly. Recognized wake/answer events are appended to
`firmware/base-station/outputs/assistant_events.jsonl`.

## Verification

176 voice/display tests passed, including wake gating, timeout, unsupported-command
rejection, listening-before-answer order, quick listening text plus RGB strips,
display-only transport and UDP loopback reassembly. Offline decoding of generated
Windows speech passed Kogane, both commands, the combined phrase, bare-command
rejection and unrelated-speech rejection. These are synthesized-speech checks;
the user's actual voice and physical LCD reception still need the steps above.

The wake-name vocabulary handling follows [Vosk's model adaptation constraints](https://alphacephei.com/vosk/adaptation).
