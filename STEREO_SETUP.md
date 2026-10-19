# Stereo demo: one person position from two webcams

Updated 2026-10-17. This supersedes the earlier independent-camera setup.

**Latest direction:** the two webcams are for wider visual coverage, while the
LD2450 supplies position. Follow [ROOM_MAPPING_DEMO.md](ROOM_MAPPING_DEMO.md) for
the new `--position-source radar` mode, outward angles, full original camera views
and coverage tests. The stereo setup below remains available as an optional mode;
changing camera angles invalidates its saved rig calibration.

## Updated dashboard

The stereo demo now opens a readable room dashboard: a large room map with one
**You** marker and path, a prominent **Depth from cameras** reading, small left/
right video previews, and a **Sensors** card. The radar defaults to the midpoint
between the configured camera positions, matching the user's approximate placement.
Its exact forward/sideways offset still needs measurement if you want to compare
room positions accurately.

| Display | Meaning |
| --- | --- |
| Person tracked | Both cameras produced a recent stereo position |
| Finding depth | A person is visible; a reliable paired match is not available yet |
| Step into view | No current person detected in the left view |
| Waiting for cameras / Check a camera | Images are missing, delayed or unavailable |
| Room radar: N detections | Fresh radar reports; amber points are separate observations |
| Room radar: Paused | Radar reports stopped; this does not mean the room is empty |
| Room position · approximate | Camera axes are assumed; measured floor alignment is still pending |

**F** toggles fullscreen, **D** shows/hides technical details, **L** locks/unlocks
the person, **C** clears the path, and **Q** saves/closes the recording. Calibration
limitations remain visible as a small note. Details include device indices,
measurement age, image-match support, host timing and raw radar status. No old
distance is displayed as a current measurement after tracking expires.

Close the currently running app with **Q** to load the UI update, then use a fresh
recording filename so earlier takes are preserved:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --baseline 0.40 --stereo-calibration calib\stereo.json --room-width 5 --room-depth 4 --radar-port COM6 --record outputs\stereo_radar_ui_take1.mp4
```

## Current saved result: ready for the distance check

The user's **18 saved corner pairs**, tablet squares **18 mm**, and device order
**left 2 / right 1** have now produced `firmware/base-station/calib/stereo.json`.
The original corner data is backed up as
`firmware/base-station/outputs/stereo_samples_backup_20261017_180534.json`.

This is explicitly a **limited-coverage demo calibration**. Device 1's horizontal
board-centre span was 74.0 px, just below the original 76.8 px heuristic. Its
geometric quality passed without loosening error thresholds: calibrated baseline
0.417 m, stereo RMS 0.253 px, median vertical error 0.191 px, p95 0.589 px.
Three held-out folds also passed, with p95 vertical errors about 0.50–1.10 px.
This supports trying the live demo; it does not establish real-world depth accuracy.

**Press Q to close the old calibration window**, then run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --baseline 0.40 --stereo-calibration calib\stereo.json --room-width 5 --room-depth 4 --record outputs\stereo_take1.mp4
```

Start standing still around **2.5–3 m away**, centred in both views. Check for one
green person marker and Person tracked, then compare at measured distances before
walking slowly. Automatic disparity search now uses this calibration's focal
length/baseline: 304 disparities, nominal near limit around 1.60 m. Keep beyond
that limit for initial checks. Room x/y still needs floor alignment for camera tilt.

**Images versus corners:** the older capture process saved all 18 pairs of corner
coordinates, not camera images. Those coordinates are sufficient for the offline
solve. Future capture runs now save raw left/right PNGs on S under
`outputs/stereo_capture/<run>/`, with paths in the saved corner JSON. This change
cannot recover images from the completed older capture run.

To repeat the offline evaluation without opening either webcam:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.stereo_calibrate --solve-only --camera 2 --camera2 1 --square-mm 18 --baseline 0.40 --allow-limited-coverage --samples outputs\stereo_samples_backup_20261017_180534.json --out calib\stereo.json
```

`--allow-limited-coverage` bypasses only the coverage heuristic and adds held-out
checks and calibration-stability checks. It retains geometric error, baseline and
camera-order gates. Quality notes persist in the calibration, and the live display
shows a demo-calibration distance-check note. Detailed results are in
`outputs/stereo_calibration_report.json`. New captures are optional if measured
distance checks pass; improve coverage later if range or alignment is inaccurate.

## What changed

- `--camera 2 --camera2 1` now selects **calibrated stereo** by default.
- One detector/tracker supplies the person's identity. Pixel correspondence in the
  rectified right image supplies depth. The map shows **one green person and trail**.
- Room defaults: **5 m along the camera wall, 4 m into the room**.
- The lenses are approximately 0.40 m apart. At a centred placement, left/right
  reference positions are x=2.30 m and x=2.70 m, with y=0 at the camera wall.
- Missing calibration, bad timing, weak image matches and a missing camera cause
  depth to be withheld. There is no automatic fallback to estimated person height.
- Optional LD2450 observations remain amber and separate for comparison.

The implementation follows OpenCV's camera calibration, stereo rectification and
disparity geometry. Metric scale comes from the **measured checkerboard squares**.
The 40 cm spacing is an independent scale check. [OpenCV documentation](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)

## 1. Fix the camera arrangement

1. Close the previous mapping window with **Q** and close other camera applications.
2. Secure the two webcams on the monitor, about 40 cm **between lens centres**.
   Keep them at approximately the same height.
3. Point both into the **same central walking area**, with substantial overlap.
   Start approximately parallel, facing straight ahead. A slight inward angle is
   possible, but keep it fixed and calibrate in that exact arrangement.
   The previous outward-angle coverage setup should be changed before stereo calibration.
4. Tilt both so the person's torso is visible; keep feet visible too if you will
   align the rig to measured floor coordinates. Do not change zoom, focus settings,
   resolution or camera angle after calibration. Disable autofocus where the camera
   software supports it, to keep lens settings stable.
5. Identify the physical left and right lenses. In this guide, left/right mean
   **looking from the camera wall into the room**, along the cameras' viewing direction.

Open PowerShell:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --camera-test
```

Briefly cover each lens to identify its panel. Use the left lens's device index
after `--camera` and the right lens's index after `--camera2`. The physical pair
may instead be devices 1 and 2 if the laptop's own webcam occupies index 0.
Both indices 0 and 1 opened together in the earlier hardware check; identify them
again after unplugging/reconnecting devices. Press **Q** before the next stage.

The commands below assume physical left=2, right=1. Substitute your actual pair
consistently in calibration and mapping. Capture requests 640x480 MJPEG at 15 FPS;
Windows uses DirectShow by default. If a device requires `--camera-api msmf`, use
that same setting during calibration and mapping. If either camera moves, recalibrate.

## 2. Display the calibration board on your tablet

1. Put the tablet and laptop on the same home Wi-Fi.
2. In a **separate PowerShell window**, run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.vision.stereo_calibrate --serve-board
```

3. On the tablet, open **http://10.0.0.66:8765/**. That laptop Wi-Fi address was
   checked on 2026-10-17; if it changes, use the IPv4 address under Wi-Fi in `ipconfig`.
   The server exposes only the generated pattern, not repository files.
4. Tap **Fullscreen pattern** if supported. Lock tablet screen orientation and
   leave browser zoom and display size unchanged throughout calibration. If the
   browser does not support fullscreen, keep its current layout fixed instead.
5. The board has **10 by 7 squares**, giving **9 by 6 inner corners**. The detector
   expects the whole board and its white border to be visible in both cameras.
6. **Measure one square with a physical ruler**, after finalizing fullscreen/zoom.
   Better: measure across five squares and divide by five. For example, five squares
   spanning 100 mm means one square is 20 mm. Use your actual result, not this example.
7. Keep the tablet rigid, reasonably bright without washed-out white squares, and
   avoid glare. Hold it still for each capture. Do not resize the pattern later.

If the page does not load, verify same Wi-Fi, server still running, and any Windows
request to allow Python on your private network. A local-file alternative is:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.stereo_calibrate --make-board outputs\stereo_checkerboard.html
```

Transfer that HTML file to the tablet, open it in a browser, then measure its
displayed squares in the same way. Keep the server window open while serving the
pattern; stop it afterwards with **Ctrl+C**.

## 3. Calibrate the actual stereo pair

The user measured **18 mm per square** on the current tablet pattern. Keep that
fullscreen/zoom/orientation fixed. If the displayed pattern size changes, measure
again and update `--square-mm`; do not reuse 18 mm automatically.

In the original PowerShell window, run:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.stereo_calibrate --camera 2 --camera2 1 --square-mm 18 --baseline 0.40 --out calib\stereo.json
```

1. Hold the tablet in the overlapping view, initially around 0.7–1.5 m away where
   the whole board is visible and sharp in both images. Adjust distance as needed.
2. Wait for **BOARD FOUND** in both panels. Check the red **0** labels identify the
   same physical board corner in both views. Both images must show the same face.
3. Hold still, then press **S** on the laptop to save a paired observation.
4. Move the tablet to a different pose, hold still, and press **S** again.
5. Capture **20–25 poses** (minimum 18). Spread them left/right and high/low, at
   different distances and with moderate tilt around both horizontal and vertical
   axes. Keep the entire board visible in both cameras. Avoid capturing many nearly
   identical front-facing views. Keep the camera rig itself fixed.
6. Press **Enter** to calculate calibration. It may take a few seconds.
7. A passing result saves `calib/stereo.json` and prints calibrated lens spacing,
   reprojection RMS and median vertical error. The estimated spacing should agree
   with your independently measured 0.40 m within the program's tolerance.
8. If calibration is rejected, read the explanation in PowerShell. Add better
   poses if coverage was poor, or restart capture after fixing wrong square size,
   blur, camera order or tablet resizing. Do not use a rejected result.

Corner observations and raw-image paths are saved in `outputs/stereo_samples.json`; raw PNG pairs go under `outputs/stereo_capture/`. Only a passing
solve writes the calibration file. Existing valid calibration is not overwritten
by a failed solve. The program checks RMS <=1.5 pixels, median rectified vertical
error <=1 pixel, vertical p95 <=2 pixels, capture diversity and baseline agreement.
These checks do not replace a measured distance test.

## 4. Run stereo tracking: one marker

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --baseline 0.40 --stereo-calibration calib\stereo.json --room-width 5 --room-depth 4 --record outputs\stereo_take1.mp4
```

Wait for tracker loading and a **Person tracked** status. Stand in the overlap
region, initially around 2–3 m away, facing the cameras. A textured shirt generally
gives more useful image detail than a featureless or reflective surface.

Expected display:

- Both rectified camera views, with the **same PERSON ID**.
- The right image marks the matched torso region, which can be smaller than the
  left camera's full person box.
- **One green marker and one trail** in the map.
- Depth from the original left camera's optical frame. Press D for correspondence support
  and host receipt-time skew.
- Before room alignment: **Room position · approximate**.

The person-height model is not used for stereo range. Initial room x/y assumes a
level rig aimed straight along +y; real camera tilt and placement require the
next step. The measured surface is the visible torso, so it is not an exact body
centre or floor-foot position. Support/spread describe image-match consistency,
not a guaranteed physical accuracy bound.

Use **L** to lock/unlock the current person, **C** to clear the trail and **Q** to
finalize the MP4 and CSV. Demonstrate one person initially. The CSV contains a
single `stereo` source per accepted measurement, with the person's ID, x/y,
optical depth, host skew, valid sample count and alignment provenance.

## 5. Align stereo measurements to the actual room

This step accounts for camera height/tilt and makes x/y comparable with the radar.
It uses **measured floor points in the LEFT camera**, together with stereo intrinsics,
to calculate the rig's orientation and position in the room.

1. Define `(0,0)` at the left end of the 5 m camera wall when looking into the room.
   x runs along that wall to 5 m; y runs away from it into the 4 m room.
2. Measure four or more spread-out floor marks visible in the left camera, using
   a tape measure or known floor dimensions. Avoid points all on one line.
3. Stop stereo tracking, then run:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.calibrate --source webcam --camera 2 --capture-width 640 --capture-height 480 --camera-api dshow --out calib\stereo_room_floor.json
```

4. Click the measured floor marks, press **Enter**, then enter each mark's actual
   room `x,y` in metres, in the order clicked. Keep this file separate from stereo.json.
5. Restart with the floor alignment:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --baseline 0.40 --stereo-calibration calib\stereo.json --stereo-floor calib\stereo_room_floor.json --room-width 5 --room-depth 4 --record outputs\stereo_room_take1.mp4
```

The footer should say **Room placement aligned to measured floor points**. No second-camera homography or manual
outward-angle setting is needed: the stereo calibration supplies relative geometry,
and the floor points supply the room pose. Moving either camera invalidates the rig.

## 6. Camera and depth acceptance tests

| Test | Action | Expected |
| --- | --- | --- |
| One person | Stand still in the overlap region | Same ID in both views; one green map marker |
| Range | Stand at several measured positions, initially around 2, 2.5 and 3 m | Depth changes in the correct direction; compare room-aligned x/y with floor marks |
| Sideways | Walk slowly left/right while visible to both | One trail moves sideways |
| Missing view | Cover one lens for more than one second | Stereo position/depth disappear; no replacement estimate appears |
| Leave overlap | Step where only one camera can see you | No live stereo depth until a reliable paired match returns |
| Recovery | Uncover lens / return to overlap | Stereo depth returns after reliable correspondence |
| Empty room | Leave both views | No live person marker; old trail may remain until C |
| Recording | Press Q and open MP4 / CSV | One stereo trajectory recorded; no separate camera1/camera2 positions |

Consumer USB webcams are **not hardware synchronized**. Pairing limits host
receipt skew to 40 ms by default, but this cannot prove exposure synchronization.
Hold still for calibration and range checks, and walk slowly for the demonstration.
Do not use this demo's coordinates for flight control. Far/near limits and texture,
occlusion, lighting, motion, focus and calibration all affect usable depth.

If only WAITING FOR RELIABLE STEREO MATCH appears, check matching camera order,
fixed lens settings, overlapping views, calibration quality and torso texture.
Use a measured stationary test before trusting any displayed distance. If image
dimensions differ from calibration, the program refuses depth until settings match.

## 7. Add the LD2450 on COM6

**Current port: COM6.** A read-only hardware check received valid LD2450 reports,
including a target. A subsequent 10-second check decoded52reports with no bad
frame footers, but observed several-second gaps. Secure the power/GND/TX-to-RX
connections and watch the freshness status; reception is verified, uninterrupted
reporting and room alignment still need checking. The diagnostic has released COM6.

Quit the current stereo display with Q, close other serial monitors, and run:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --camera 2 --camera2 1 --baseline 0.40 --stereo-calibration calib\stereo.json --room-width 5 --room-depth 4 --radar-port COM6 --record outputs\stereo_radar_take1.mp4
```

Walk slowly in front of the radar; fresh reports should appear in the Sensors card, and detected
targets appear in amber. The Sensors card shows a detection count when reports are fresh. Green remains the stereo person. Empty fresh radar
reports are valid when no target is detected. Paused (STALE under D) means reports stopped, not
proof of an empty room. Check secure wiring and the5V supply under load if gaps persist.

Defaults place the radar at `(2.5,0)`, facing into the room; measure its
actual table location and set `--radar-x`, `--radar-y`, `--radar-yaw` as needed.

Radar observations stay amber so you can compare them with the one green stereo
person. Room alignment should be completed before claiming positional agreement.
No flight commands are sent by this demonstration.

## Verification status

- Both physical camera feeds have previously captured together. The actual rig now has a limited-coverage calibration from 18 saved corner pairs; a measured depth walk test remains pending.
- Automated tests recover a known 0.40 m baseline from projected checkerboard poses,
  recover a known 4 m depth from actual SGBM correspondence on shifted textures,
  reject unrelated images and stale/reused/skewed frame pairs, and verify floor-pose
  conversion. A recorded runner test verifies one identity and loss of depth when
  a camera fails. These use known synthetic geometry, not a claim of live accuracy.
- Layout previews are explicitly NOT LIVE. Recordings under outputs are ignored by Git.

The earlier independent-camera diagnostic is retained only via
`--independent-cameras`. Use the default calibrated stereo mode for this demo.
