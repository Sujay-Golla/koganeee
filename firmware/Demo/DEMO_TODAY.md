# Today's demo: room tracking and two voice commands

**Current schedule:** [FINAL_DEMO_PLAN.md](FINAL_DEMO_PLAN.md) is the 2–3 hour
finish plan with the battery setup now ready, laptop audio selected and battery
sensing/onboard camera deferred. Follow its flight checks and recording order.

**Real weather update:** [WEATHER_DEMO.md](WEATHER_DEMO.md) replaces the preset
with Open-Meteo current conditions and today's high/low. Internet is required
for weather; the voice recognizer and saved tasks stay local. Older preset and
picture descriptions below are historical.

**Latest task-list app:** [TASKS_DEMO.md](TASKS_DEMO.md) replaces the picture command
with **Show me my tasks for today**, plus voice add/complete/rename/delete/undo.
Use `--device 3` for the confirmed laptop microphone. Older picture instructions
below describe the previous demo.

**Current voice/LCD flow:** follow [VOICE_LCD_DEMO.md](VOICE_LCD_DEMO.md). Say
**Kogane**, wait for the green **Listening…** card on the FC LCD, then say one of
the two commands. Every command now needs a wake word. User confirms the power
issue was manually verified and is fine; proceed with that verified arrangement.

## What is ready

- Radar position with two original camera views for wider coverage (current mode); optional single-camera and stereo modes remain available.
- Optional LD2450 reports directly through a USB-to-TTL adapter, drawn in amber.
- MP4 recording of the overlay, plus a CSV of measurements.
- Offline laptop microphone recognition of two phrases, laptop speech, and LCD cards.

The tracking display observes people; it does not reconstruct walls or perform SLAM.
In the current mode, radar supplies the person position and cameras provide independent visual coverage.
Weather uses the live service; the second app is the saved task list. These tools do
not send flight commands. Do not launch the main base-station control loop for these clips.

## 1. Start with the webcam

1. Put the webcam on the monitor, facing into the room. Keep it fixed.
2. Tilt it so a standing person's entire body, including feet, is visible in the
   walking area. A cropped seated/head-only view gives poor distance estimates.
3. Close Camera, Teams, Zoom, or other programs using that webcam.
4. Open PowerShell and enter:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 0 --record outputs\room_webcam.mp4
```

5. If it opens the laptop camera instead of the external webcam, press **Q** in the
   display window, then repeat with `--camera 1`. Try `2` if needed.
6. Walk slowly left/right and toward/away from the camera. A cyan person marker and
   trail should move on the right. Press **L** to lock the current person, **C** to
   clear the trail, and **Q** to finish and save the recording.

Outputs are `firmware/base-station/outputs/room_webcam.mp4` and `room_webcam.csv`.
Choose a new filename for each take; an existing filename is overwritten.

The default plot is a **5 m wide by 4 m deep reference area**, with the camera in
the middle of the near wall. It is not a measured room boundary. Until floor
calibration, distance uses an approximate person-height model (default 1.7 m).
Change it with `--person-height 1.75`, for example. Do not present these initial
coordinates as measured accuracy.

## 1B. Two webcams for wider coverage, radar for position (current mode)

Follow [ROOM_MAPPING_DEMO.md](ROOM_MAPPING_DEMO.md) for the latest setup.
The webcams cover different parts of the room, while the LD2450 supplies the one
main position and distance. Camera images remain full and unrectified; either
camera can lose sight of the person without stopping radar position.

1. Angle left device 2 toward the left and right device 1 toward the right, with
   a little overlap around the middle. Keep the radar between them facing forward.
2. Q the old app. Use `--position-source radar --camera 2 --camera2 1 --radar-port COM6`.
3. Press V to enlarge both views and check the left/middle/right walking coverage.
4. Return to the map with V; check radar position along the same route.
5. Use one person initially. Missing radar reports withhold position; cameras do
   not fabricate a replacement position. Q finalizes the MP4 and CSV.

This mode needs no stereo calibration or floor homography. The saved stereo mode
remains available; recalibrate it if you return after changing the camera rig.
Room dimensions remain 5 m along the sensor wall and 4 m deep.

## 2. Connect the LD2450 through USB-to-TTL

No connection to the flight controller is required. Unplug the adapter from USB
while making these connections, and identify pins by their labels, not wire colors.

| LD2450 pin | Connect to |
| --- | --- |
| 5V | Adapter's verified USB **5V output**, if rated to supply more than 200 mA |
| GND | Adapter GND |
| TX | Adapter RX / RXD |
| RX | Leave unconnected for this read-only demo |

Leave the adapter's TX disconnected. The radar requires **5 V power** and uses
**3.3 V TTL serial signals**. A voltage jumper may change the power output, serial
logic, or both depending on the adapter; identify the adapter before moving it.
Do not assume setting a jumper to 5V also gives suitable serial levels, and do not
power the radar from a 3.3V pin. If an independent regulated USB 5V supply is used,
connect its ground to radar GND and adapter GND; leave the adapter power pin unused.

These requirements and the default 256000-baud serial rate are specified by
[Hi-Link](https://www.hlktech.com/en/Goods-352.html). The program sets 256000 8N1.
It sends no configuration commands, so a previously changed radar baud rate must
be restored separately.

1. Secure the radar upright, antenna face toward the room and clear of the monitor
   or metal objects. Do not lay the antenna facing the ceiling. The manufacturer
   recommends a mounting height of 1.5–2 m; a lower table position is a provisional
   demonstration placement and must be checked with actual walking tests.
2. Aim it in the same direction as the webcam. Keep both near the center of the
   same wall. Measure their horizontal separation if you want to compare positions.
3. Plug the USB adapter into the laptop. In the same PowerShell window, run:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
```

4. Note the adapter's COM number. It may differ from the ESP32's COM13. Close any
   serial monitor or Hi-Link utility using that port.
5. Stop the webcam-only program with **Q**, then run the combined display. Replace
   `COM7` below with the adapter's actual port:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 0 --radar-port COM7 --record outputs\room_camera_radar.mp4
```

6. Walk in front of both sensors. The status should become **LIVE**, with amber
   radar points as well as the cyan camera position. Empty reports are valid when
   no target is detected. If no reports arrive, check TX-to-RX, ground, measured
   5V, the COM port, and whether another program owns it.
7. Disconnect the radar's USB cable as a brief check: its points should expire
   instead of remaining falsely live. Reconnect and restart the program to reopen
   the serial port. There is no automatic reconnection yet.

In single-camera mode, default sensor origins coincide at `(2.5, 0)` in the 5 m wide reference plot. For a
measured room, add `--room-width WIDTH --room-depth DEPTH`, using metres. Coordinates
have x increasing to the right when looking into the room, and y increasing into
the room from the sensor wall. Camera and radar positions can be set independently:
`--camera-x`, `--camera-y`, `--radar-x`, `--radar-y`, with orientation in degrees via
`--camera-yaw` and `--radar-yaw`. At zero degrees they face along +y.
Check left/right with a real walk before describing the two tracks as aligned.

## 3. Improve camera positions with floor calibration

Do this after the live view works, if time permits:

1. Mark four or more measured floor positions spread across the visible walking
   area, not all on a line. Measure their x,y in the coordinate system above.
2. Keep the camera fixed, then run (use the same camera index as the live display):

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.calibrate --source webcam --camera 0 --out calib\demo_floor.json
```

3. Click each marked floor point in the image, then press **Enter**. In PowerShell,
   enter that point's measured `x,y` in metres when prompted, in the same order.
4. Launch the overlay with `--homography calib\demo_floor.json` added to its command.
5. Walk to other measured floor marks and compare. Calibration-point fit alone does
   not establish accuracy elsewhere. Moving or tilting the camera invalidates it.

## 4. Rehearse the two voice commands on the laptop

The local environment already has the recognition dependencies and English model.
The assistant runs independently of the webcam program; close the mapping view
first for a simpler recording setup.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant
```

Wait for the listening status, then say one phrase at a time:

- **Show me the weather today**
- **Show me a picture**

The preview should change and laptop speakers should answer. Weather defaults to
Toronto, 12°C, cloudy, clearly labeled as a preset forecast. This is not live weather.
The picture is a preset illustration; supply a local image with `--picture PATH`.
Say **Kogane** first and wait for the listening card. Press **Q** to exit.

If the wrong microphone is selected, run with `--list-mics`, then add `--device N`
using the desired input device number. Enable Windows microphone permission if
capture is blocked. **W** and **P** are keyboard rehearsal controls; those actions
are labeled KEYBOARD, so do not present them as recognized voice input.

## 5. Send the voice cards to the FC LCD

The user confirms the power issue has been manually verified and is fine. Use that
verified setup for the FC LCD. The earlier power review remains in the project
history; it is not an outstanding approval request for this demonstration.

Once the ESP32 is on Wi-Fi and the LCD is safely powered:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --host 10.0.0.47
```

Use the ESP32's current address if it changed. A ready card should appear; say
**Kogane**, wait for **Listening…**, then speak one command. Repeat the wake word
for the second command. **R** resends the current card if the screen needs refreshing.
The host option transmits display packets only. It has no arm, servo, or flight action.
Actual LCD delivery and your spoken-voice test remain to be confirmed on hardware.

## Recording sequence

1. Record a 20–30 second mapping take: empty room, enter, walk across, walk toward
   the sensors, leave. Keep the camera and radar status labels visible.
2. Record the two voice interactions as a separate take, showing the recognized
   phrase and response. Say that response content is preset for this demo.
3. A flight clip is a separate milestone requiring power repair, motor/order/direction,
   orientation, RC arming/disarming and failsafe checks. The mapping and assistant
   clips can be recorded without the aircraft powered.

## Verification status, 2026-10-17

- Real webcam capture and person detection passed; an 8-second MP4 and CSV were saved.
- A 16kHz laptop microphone capture passed. Both command phrases were recognized from
  synthesized test speech. Recognition from the user's actual speech is still pending.
- Demo and existing display tests: 132 passed. Preview cards and overlay were inspected.
- Actual LD2450 serial reports and physical LCD cards are still pending hardware checks.
- Earlier independent-camera test: both indices 0 and 1 captured together in a six-second live
  connection test. An eight-second run with both independent person trackers saved
  a 121-frame MP4 and CSV; camera 1 recorded person fixes during that short test.
  Full-body walking, floor calibration and alignment of the intended two webcams
  remain user checks. Seventeen demo/multicamera tests passed, including loss of
  one camera while its peer continues, target expiry and recording finalization.
  Including the existing projection/geometry tests, the final targeted run passed
  **41 tests**.
- Current two-camera mode is calibrated stereo, with **50 targeted tests passed**
  on known geometry, image correspondence, pairing, room alignment and one-person
  recording/failure handling. The actual rig's tablet calibration and measured
  live depth was pending at that stage. Subsequently, the 18 saved real corner
  pairs produced a limited-coverage calibration with held-out checks passed;
  **56 targeted tests now pass**. A measured live-depth check remains pending.
  See `STEREO_SETUP.md` for the current procedure.
- Layout-only previews are explicitly labeled NOT LIVE and must not be used as sensor proof.

For a fresh environment, install the project extras with `pip install -e ".[demo]"`
and download/extract `vosk-model-small-en-us-0.15` into `firmware/base-station/models/`
from the [official Vosk models page](https://alphacephei.com/vosk/models). Existing
vision dependencies and `yolov8n.pt` are also required for the webcam tool. Model
downloads and recordings are ignored by Git.
