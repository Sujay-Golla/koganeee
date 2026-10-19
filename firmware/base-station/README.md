# Laptop applications

The laptop runs voice recognition, spoken replies, weather, daily tasks and the room dashboard. The current demo uses two webcams and an LD2450 connected through USB-UART. The ESP32 receives LCD cards over Wi-Fi.

## Install

Run these commands from `firmware/base-station` in PowerShell. The tested environment uses Python 3.13.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[demo,vision,screen,radar,character-voice,dev]"
.\.venv\Scripts\python.exe -m kogane_base.tools.setup_kokoro_voice
```

Reuse the existing `.venv` if it works. Download `vosk-model-small-en-us-0.15` from the [Vosk model list](https://alphacephei.com/vosk/models) and extract it into `models/vosk-model-small-en-us-0.15/`.

Kokoro setup downloads the default Natural voice. Add `--speech-style normal` to use Windows speech instead, or `--mute` for a silent test. Weather needs internet access. Recognition, task storage and speech synthesis run locally.

## Voice assistant

Find the laptop microphone, then run the assistant with its device index and the ESP32's current Wi-Fi address.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --list-mics
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3 --host 10.0.0.47
```

Device `3` and `10.0.0.47` are examples from the development setup. Omit `--host` for laptop preview only. The LCD needs its normal 5 V supply and the ESP32 display stage enabled.

Say **Kogane**, wait for **Listening**, then give a command.

- Say **Show me the weather today** to fetch the forecast.
- Say **Show me my tasks for today** to open the saved list.
- Say **New task buy groceries** to add an item.
- Say **Complete task one** or **Delete task one** to edit it.
- Say **Stop listening** to end task editing.

Task replies open a 30-second follow-up window. Weather requires another wake word. Tasks persist in `data/tasks.json`. Use `--city "Ottawa" --country CA` to change the weather location. Press **F** for fullscreen and **Q** to close.

Details are in the [voice/LCD guide](../Demo/VOICE_LCD_DEMO.md), [task guide](../Demo/TASKS_DEMO.md), [weather guide](../Demo/WEATHER_DEMO.md) and [voice options](../Demo/VOICE_STYLE.md).

### Onboard microphone

The stationary board-microphone path was demonstrated separately. It sends ESP32 audio to the laptop for recognition. The laptop still provides spoken output.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.esp_mic_check --host 10.0.0.47 --seconds 12
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --mic-source esp32 --host 10.0.0.47
```

Run the recording check first and listen to the saved WAV. Stop other UDP/5005 listeners before either command. Do not pass a laptop `--device` in board-microphone mode. See the [board microphone guide](../Demo/BOARD_MIC_TEST.md). Motor-noise performance remains unverified.

## Room mapping

The radar supplies human positions. The webcams provide wider coverage and object recognition. Use the actual camera indices and radar port.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --radar-port COM6 --room-width 5 --room-depth 4 --record outputs\room_take1.mp4
```

- Press **V** to enlarge the camera views.
- Press **F** for fullscreen or **D** for details.
- Press **C** to clear the trail.
- Press **Q** to save and close.

This mode needs no stereo calibration. The room dimensions and radar placement must match the real setup. Use a fresh filename for each take. Add `--record-width 1920` for Full HD output.

The [room guide](../Demo/ROOM_MAPPING_DEMO.md) covers placement and recording. The [object guide](../Demo/OBJECT_MAPPING.md) covers furniture detection and floor calibration. Detecting a chair does not establish its floor position. The [stereo guide](../Demo/STEREO_SETUP.md) documents the separate depth experiment.

## Flight-controller telemetry

Stop other UDP/5005 listeners and run this passive check.

```powershell
.\.venv\Scripts\python.exe verify_wifi.py listen --seconds 30 --require-fc
```

The ESP32 must forward MAVLink data to this laptop's current IP. Expect fresh FC status and heading. The tool sends no flight commands. The reported battery voltage remains invalid until the board's sensing hardware is fixed.

## Experimental tools

The main orchestrator at `python -m kogane_base` contains fusion, setpoint and failsafe experiments. Its general voice pipeline remains a stub. It is separate from the working assistant and mapping applications above. It is not a validated autonomous flight controller.

The standalone vision tool supports webcam, file and MJPEG inputs, plus optional pose and FaceID experiments.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.demo --source webcam
.\.venv\Scripts\python.exe -m kogane_base.vision.demo --pose
.\.venv\Scripts\python.exe -m kogane_base.vision.demo --faceid
.\.venv\Scripts\python.exe -m kogane_base.vision.calibrate --source webcam --out calib/floor.json
```

Use `--help` for source selection, face enrollment and calibration options. Face embeddings are stored in ignored local files. Get consent before enrolling another person. Position accuracy depends on camera placement, visible floor contact and calibration.

## Code and local data

- `tools/` contains the assistant, mapping apps and bench checks.
- `vision/` contains detection, tracking, stereo and floor projection.
- `tracking/` contains the radar parser and serial input.
- `fusion/` and `link/` contain the experimental control components.
- `audio/`, `screen/` and `protocol.py` handle media and KGN messages.
- `config.py` holds orchestrator settings. Set environment variables before starting the process.

Models, calibration, recordings, face data and tasks stay local. The latest verified snapshot passed 741 Python tests. Run the suite after installing the `dev` extra.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
