# Finish the demo with the FC powered off tonight

**Superseded 2026-10-18:** battery setup is now ready. Use
[FINAL_DEMO_PLAN.md](FINAL_DEMO_PLAN.md) for the current 2–3 hour schedule,
laptop-mic/LCD recording, optional board-mic/ToF checks, remaining motor/control
checks and conditional first flight. The overnight schedule below is historical.

Prepared 2026-10-18. Goal: finish the mapping clip and voice rehearsal now, leaving
physical LCD checks and filming for the next battery-powered session.

**Microphone decision:** use the laptop microphone for the main demo video.
Treat the [stationary board microphone check](BOARD_MIC_TEST.md) as a separate
optional capability clip. Do not present its software-only simulation as a
physical-board demonstration; record that clip after the real audio test passes.

## What can be finished now

| Clip / task | Needs the aircraft battery? | Completion check |
| --- | --- | --- |
| Radar + two webcams + chair recognition | No; laptop USB powers these devices | Saved MP4 plays and shows a moving radar track plus real camera detections |
| Kogane + both spoken commands | No; laptop preview supports the complete voice flow | Both commands succeed after a wake word in three consecutive rounds |
| Shot framing, narration, project overview | No | Phone framing and audio checked; opening shots recorded |
| Physical LCD reception and orientation | Yes, with your existing display power arrangement | Ready, Listening and both answer cards visible and correctly oriented |
| First flight | Separate milestone | Remaining propulsion, arming and failsafe checks completed before attempting it |

Budget roughly 30-60 minutes tonight and 15-30 minutes for the LCD clip next
session if the voice rehearsal passes and the existing display link works.
These estimates exclude flight preparation and troubleshooting.

## 1. Rehearse real voice recognition first

Keep the FC off. Use your normal laptop microphone and speakers. Open PowerShell:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3
```

Omitting `--host` selects laptop preview only: no display destination/socket is
opened. This still uses the real microphone, your pronunciation profile and
laptop speech. Do not add `--no-mic` for this test.

Input 3 is the currently verified laptop Realtek Microphone Array MME device;
Windows otherwise defaults to USB Audio. Check `--list-mics` if indices change.

1. Wait until **Say Kogane** appears.
2. Say **Kogane** naturally. Wait for the green **Listening** card.
3. Say **Show me the weather today**. Wait for the card and spoken answer.
4. After speech finishes, say **Kogane**, wait for Listening, then say
   **Show me my tasks for today**. After the reply, while the footer says
   **Listening**, create tasks directly with **New task buy groceries**. Task
   follow-ups stay active for 30 seconds after replies. Details:
   [TASKS_DEMO.md](TASKS_DEMO.md).
5. Repeat the pair three times at the distance you will use while filming.
6. Say **Stop listening**, then try a command without a wake: it should not run.
   Say Kogane once and remain silent: the listening state should time out.
7. Press **Q** to close. If recognition misses, save the exact terminal
   `Heard: ...` line; fix that tonight, before introducing the LCD tomorrow.

The personal `calib\wake_pronunciation.json` is already present and loads
automatically. Its offline result is not a substitute for this live rehearsal.
If nothing is heard, list microphones and select the appropriate input:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --list-mics
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device N
```

Replace N with the actual input number. Keep that same `--device N` tomorrow.
Press **F** for fullscreen. Keyboard A/W/P are labelled rehearsal controls;
do not use them for footage presented as a voice demonstration.

## 2. Record the finished mapping clip tonight

Plug both webcams and the USB-to-TTL radar adapter into the laptop. Keep the
working radar wiring and placement. Close other camera apps and COM6 monitors.
The aircraft can remain completely disconnected.

From the same base-station folder:

```powershell
$take = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --baseline 0.40 --camera-yaw 15 --camera2-yaw -15 --radar-port COM6 --room-width 5 --room-depth 4 --map-objects --record-width 1920 --record "outputs\room_demo_$take.mp4"
```

These are the last documented device indices and placement defaults. Preserve
any different radar placement settings from your currently working command.
If USB devices enumerate differently, use the current camera indices/COM port.
Each fresh invocation of both lines gives a new take filename.

1. Check both views; press **V** to enlarge them if needed, then V to return.
2. Put a recognizable chair in a clear camera view. Leave the webcam/radar
   arrangement fixed for the recording.
3. Press **F** for fullscreen and **C** to clear the walking trail.
4. Pause for a clean opening view, then walk left/right and toward/away from the
   radar. Use one person in view for an unambiguous track.
5. Pause where the chair box is visible. Show yourself moving between camera
   coverage areas while the radar supplies the map position.
6. Record about 30-45 seconds, then press **Q** to finalize the MP4 and CSV.
7. Open the saved MP4 immediately and check the beginning and end. The built-in
   recording contains the dashboard, without microphone narration. Record any
   narration separately or capture it with your phone.

Current feet/chair bases are partly hidden, and object floor calibration has
been deferred. This command shows **chair detection in the camera views** and
**person position on the map from radar**. It does not place the chair on the
floor map or reconstruct the room. Present those actual capabilities in the video.
No new stereo calibration is needed. Details: ROOM_MAPPING_DEMO.md and
OBJECT_MAPPING.md.

## 3. Prepare the physical LCD shot now

- Choose a phone position that clearly shows the LCD and lets the viewer hear
  you and the laptop speaker. Leave space for your hand without covering the LCD.
- Use steady room lighting. Record a short audio/framing test with the laptop
  rehearsal visible, then play it back.
- Film a short overview of the unpowered aircraft, the two cameras and radar.
- Assemble the overview and mapping clips in your video editor now; leave a
  25-40 second slot for the physical LCD interaction.
- Use captions such as **Radar person tracking**, **Camera chair detection** and
  **Offline voice recognition / live weather**, and **Voice-editable tasks**.

Weather now fetches Toronto current conditions and today's high/low from
Open-Meteo. Keep the laptop online. See [WEATHER_DEMO.md](WEATHER_DEMO.md).
The second app is a real saved task list. Rehearse adding a task, showing the
list and marking one done tonight; [TASKS_DEMO.md](TASKS_DEMO.md) has the commands.

## 4. Next battery-powered session: verify once, then film

1. Keep props removed for the stationary LCD recording. Power the FC using the
   already verified arrangement; monitor the replacement battery externally.
2. Put the laptop and ESP32 on the same home Wi-Fi. Close the rehearsal process
   and other programs sending LCD updates.
3. From the base-station folder, run:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.demo_assistant --device 3 --host 10.0.0.47 --lcd-rotation 180 --lcd-mirror-x
```

4. Use the ESP32's current IP if it changed from 10.0.0.47. Retain any microphone
   flags that passed rehearsal.
5. Confirm **Say Kogane** on the physical LCD. Check the lettering. If it still
   needs a horizontal reflection, press **H** once and check again; for later
   launches use `--no-lcd-mirror-x` if mirror OFF was correct. **R** resends a card.
   The laptop preview stays upright and cannot confirm the LCD's orientation.
6. Run one complete weather/tasks interaction while watching the actual LCD.
   If the laptop responds but the LCD does not, check the address/display path;
   do not retune working voice recognition for that symptom.
7. Start the phone recording. Say Kogane, pause for Listening, request the weather,
   allow the reply to finish, then repeat Kogane and request today's tasks. Hold
   the list for a few seconds. Keep the full transitions in the clip.
8. Press Q, disconnect the battery, then add the phone clip to the prepared edit.

No ESP32 reflash is planned for these steps. Physical LCD reception and the latest
orientation correction are still pending verification. Detailed troubleshooting:
VOICE_LCD_DEMO.md.

## Scope of the finished video

A complete project demonstration can contain the overview, actual mapping clip
and physical voice/LCD clip. A flight clip is optional and remains separate:
motor order/direction, propulsion suitability, arming and armed failsafe have not
yet been confirmed. See FIRST_FLIGHT_PLAN.md for that work. If those checks are
not finished, film the functioning stationary system and describe flight as
the next milestone.
