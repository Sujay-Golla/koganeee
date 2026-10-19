# Camera object mapping: chair-first test

Updated 2026-10-17. Extends the working radar + two-camera dashboard.

## What it does

- Radar continues to supply the person's position and walking path.
- Each webcam detects chairs, sofas, benches, beds, dining tables, suitcases and
  potted plants using the existing YOLOv8n model. Start with **one ordinary chair**.
- Calibrated cameras place labelled blue object symbols on the room map. These
  are **approximate floor positions**, not measured object outlines, sizes or heights.
- An object needs repeated observation before it appears. A unique nearby match
  of the same class can join observations from both cameras. This is approximate
  spatial matching, not guaranteed recognition of an individual chair.
- A hidden object becomes an outlined **last-seen** marker after one second and
  expires 12 seconds after its last accepted observation. Stand in front of the
  chair to demonstrate this. The system cannot know whether a hidden chair moved.
- O clears the remembered objects. C still clears only the person's path.

The model does not detect every possible obstacle. An unmarked area is not known
to be clear, and this display does not drive flight or collision avoidance.
The LD2450 reports motion targets; it does not supply furniture class labels.

## Fullscreen clarity

Restart the dashboard to load the new renderer. F now redraws fonts and map graphics
at the window's actual pixel resolution, up to 3840x2160, with Windows DPI awareness.
It no longer enlarges a finished 1280x720 dashboard bitmap. Camera pictures still
contain only the detail captured by the webcams; increasing dashboard resolution
does not add detail to a 640x480 source image.

If automatic window sizing is unavailable, add `--dashboard-width 2560` (or 1920
or 3840 for your display). Recordings keep a fixed size even when the window changes.
Add `--record-width 1920` for Full HD recordings; the default stays 1280x720.

Example recognition test with a new Full HD recording filename:

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --radar-port COM6 --map-objects --record-width 1920 --record outputs\room_objects_hd_take1.mp4
```

Keep your `--object-floor` / `--object-floor2` flags if calibrated. This command
without them runs recognition only. Q the previous dashboard before restarting.

## Can radar provide the camera calibration?

User confirmed chair recognition works, but feet and chair bases are currently
partly/completely cut off. This framing prevents the current floor-position method.
Tilt the cameras down or move them higher so they see the relevant floor contacts.
The known floor points and the chair base must all be visible for manual calibration.

A possible future guided calibration would pair your image foot point with your
radar x/y at several stationary, spread-out positions, fit a floor mapping, then
validate it at additional positions. That guided capture workflow is **not yet
implemented**. It would inherit radar error, body/foot reference differences,
timing error and bounding-box error; it needs visible feet and enough coverage,
with bad or ambiguous samples rejected. Manual measured floor marks remain the
implemented calibration method.

One radar position of a person does not establish the depth of an unrelated chair.
With bases hidden, a camera can show left/right image placement, but a dependable
metre-valued front/behind location needs additional geometry or depth information.
The [OpenCV floor-plane mapping explanation](https://docs.opencv.org/5.0/tutorials/features/homography/homography.html)
describes the planar transformation used by the existing calibration.

## 1. Check chair recognition first

Press Q in the current dashboard, then run from PowerShell:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --radar-port COM6 --map-objects
```

1. Put one chair on the floor where a camera can see its whole base/legs.
2. Press V to enlarge the video views. Look for a labelled **Chair** box.
3. Test each view by moving the chair to its side of the room.
4. At this stage the camera caption says **Floor calibration needed**. Boxes work,
   but no object is placed on the floor plan until that camera is calibrated.
5. Press Q to release the cameras before calibration.

Recognition can miss unusual chairs or label objects incorrectly. Try a clear,
well-lit, unobstructed view first. A partly clipped base is not mapped.

## 2. Prepare four measured floor marks for the left camera

The room is 5 m along the camera wall and 4 m deep. Use this coordinate system:

- Stand behind the cameras and look into the room.
- x = metres from the left side wall toward the right side wall (0 to 5).
- y = metres away from the camera wall into the room (0 to 4).

Place at least four tape marks on the floor, spread out around the chair-test
area, forming a broad rectangle or quadrilateral. All must be visible in the left
camera. **The chair's base must stay inside the region enclosed by these marks.**
Tilt the camera down enough to see the floor contacts. Keep it fixed afterward.
You do not need a checkerboard, stereo overlap, or a camera-height measurement.

For example, if these physical locations are visible and tape-measured:

| Mark | Room coordinate to type |
| --- | --- |
| A: x1 m, y1 m | `1,1` |
| B: x3 m, y1 m | `3,1` |
| C: x3 m, y3 m | `3,3` |
| D: x1 m, y3 m | `1,3` |

These numbers are only an example. Use your actual measured marks, and choose a
different rectangle if necessary. More spread-out marks improve the useful area.
Do not click chair corners, walls, or a point above the floor.

## 3. Calibrate the left webcam (device 2)

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.calibrate --source webcam --camera 2 --capture-width 640 --capture-height 480 --capture-fps 15 --camera-api dshow --out calib\objects_left.json
```

1. The tool freezes one image. Click marks A, B, C, D in that order.
2. Press Enter after the four clicks. R resets the clicks if needed.
3. Return to the terminal. For point 1, type A's measured `x,y`, then Enter.
4. Repeat for B, C, D in exactly the same order.
5. Confirm that `calib\objects_left.json` was saved.

The reported error measures the points used to fit the map. A near-zero number
with four points does **not** establish position accuracy. Verify a separate
measured chair location in step 5 below.

## 4. Calibrate the right webcam (device 1)

Choose four floor marks visible in the right camera. They may differ from the
left camera's marks, but use the **same room origin and x/y directions**.

```powershell
.\.venv\Scripts\python.exe -m kogane_base.vision.calibrate --source webcam --camera 1 --capture-width 640 --capture-height 480 --capture-fps 15 --camera-api dshow --out calib\objects_right.json
```

Repeat the clicking and coordinate entry. You can start with just the left camera
calibrated: omit `--object-floor2` in the next command. The right view will still
detect objects without placing them on the map.

## 5. Run the combined object map

```powershell
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --radar-port COM6 --map-objects --object-floor calib\objects_left.json --object-floor2 calib\objects_right.json --record outputs\room_objects_take1.mp4
```

1. Place the chair inside the calibrated floor region. Leave its base visible.
2. Watch for a blue **Chair** marker. The terracotta person marker stays radar-based.
3. Check an additional tape-measured chair-base position that was not a calibration
   point. The marker is based on the bottom-centre of the detected box, so compare
   against that approximate visible base location, not the centre of its seat.
4. Move the chair left/right and nearer/farther. Its marker should follow after
   fresh observations. A large move can temporarily leave an old outlined marker;
   press O if needed. Small position jitter is expected.
5. Walk between the camera and chair. Its last observed position should remain
   briefly, labelled with its age, then expire if neither camera sees it again.
6. Show one chair in each camera's covered area. Test the overlap with one chair
   before adding several nearby chairs; approximate cross-camera matching can
   merge nearby same-class objects or leave duplicates when calibration disagrees.
7. Press Q to save and close. Pick a new take filename for subsequent recordings.

The MP4 contains the dashboard, the same-name CSV contains radar samples, and
`room_objects_take1_objects.csv` contains fresh camera object observations with
class, camera, confidence, approximate position and source. Remembered positions
are not logged again as fresh observations. No object memory persists across runs.

## Placement and limits

- Moving a webcam, changing its angle/zoom or changing capture dimensions requires
  a new floor calibration. Moving the cameras into top corners later is supported
  by separate per-camera calibration; stereo spacing/overlap is unnecessary here.
- Keep any measured `--radar-x`, `--radar-y` and `--radar-yaw` settings from your
  working command. The camera floor coordinates and radar placement must use the
  same room origin; floor calibration does not automatically align the radar.
- Floor projection only works when the detected base is actually on the calibrated
  floor. A plant on a table, a hidden chair base, or a wrong bounding box can produce
  a wrong location. Avoid such objects for this demonstration.
- The code rejects clipped bases, low-confidence results, floor points outside the
  calibration region and bases covered by a detected person. These checks cannot
  catch every occlusion. Verify the actual camera images with V.
- If a camera's delivered image size differs from calibration, D shows the required
  new size and that view contributes no map positions until recalibrated.
- This is a labelled object-location demo. It does not reconstruct walls, furniture
  geometry, floor coverage/free space, object heights or a 3D obstacle map.

## Verification

83 targeted checks pass, including native-density 1080p/1440p/4K drawing, automatic
window sizing, fixed Full HD recording from a larger dashboard, independent floor projections, two-camera
spatial association, separate nearby chairs in one view, missing calibration,
capture-size mismatch, occlusion, stale frames, expiring memory, object CSV source
and the existing radar/stereo/geometry checks. A local CPU model smoke test uses
an empty generated image only. Actual chair detection and position accuracy still
need the physical checks above; the labelled layout preview is example data.

The supported object names follow the model's [COCO classes](https://docs.ultralytics.com/datasets/detect/coco/).
