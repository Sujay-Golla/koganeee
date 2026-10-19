# Room demo: radar position and two cameras for wider coverage

**Recording preparation:** [DEMO_RECORDING_PLAN.md](DEMO_RECORDING_PLAN.md) gives
a Full HD recording command with a fresh take filename and a shot sequence.
The laptop-powered cameras and radar can record while the FC remains off.

Updated 2026-10-17. This is the current recommended mode for the user's demo.

**New: camera furniture/object mapping.** Follow [OBJECT_MAPPING.md](OBJECT_MAPPING.md)
to detect chairs and other floor-standing objects, calibrate each camera's floor
view, and add approximate labelled positions to this same dashboard. Radar still
supplies the person track. The object mode is opt-in with `--map-objects`.

Fullscreen now redraws at the actual window pixel size (up to 4K) with Windows DPI
awareness. Q and restart the old app to load it. `--dashboard-width 2560` overrides
automatic sizing if needed; `--record-width 1920` selects fixed Full HD MP4 output.
Source webcam detail is separate from dashboard sharpness.

## What each sensor does

- **LD2450 on COM6:** the main position, distance and walking trail in the 5x4 m room.
- **Left webcam (device 2):** people detection toward the left part of the room.
- **Right webcam (device 1):** people detection toward the right part of the room.

The two cameras are independent visual views. Position continues when one or both
cameras lose sight of the person, as long as radar reports remain available.
Images are the original camera frames, with no stereo rectification or stereo crop.
This mode does not load the stereo calibration, require image synchronization or
match identities between cameras. Boxes in two views never become two map positions.

## 1. Place the sensors for coverage

1. Keep the webcams about 40 cm apart on the monitor.
2. Looking from the sensor wall into the room, point the left camera toward the
   left area and the right camera toward the right area. Try about **15–25 degrees
   outward** initially, then adjust based on the actual video views.
3. Keep a little overlap around the centre so your walking route stays visible in
   at least one camera. Both cameras do not need to see you simultaneously.
4. Place the LD2450 between them, upright and facing straight into the room. It
   should cover the walking area independently of where the cameras are pointing.
5. Check the USB power/GND/TX-to-RX connections stay secure while you move it.

The camera wall is **5 m wide**, with **4 m depth** into the room. Default camera
references are x2.3 and x2.7, y0; radar defaults to their midpoint x2.5,y0. If it
is forward on the table, set the measured `--radar-y`, for example `0.30` only if
it is actually 30 cm forward. `--radar-x` and `--radar-yaw` set its other placement
values. Camera angles do not control radar position.

Moving/angling the webcams is fine in this mode. If you return to stereo later,
recalibrate the changed rig. The existing stereo calibration file is preserved.

## 2. Run the radar-position dashboard

Close the old display with **Q**, and close any serial monitor using COM6. Run:

```powershell
cd C:\Users\sujay\OneDrive\Documents\koganeee\firmware\base-station
.\.venv\Scripts\python.exe -m kogane_base.tools.mapping_demo --position-source radar --camera 2 --camera2 1 --baseline 0.40 --camera-yaw 15 --camera2-yaw -15 --radar-port COM6 --room-width 5 --room-depth 4 --record outputs\room_editorial_take1.mp4
```

Use the actual left/right camera indices if they change. No `--stereo-calibration`
or floor-homography file is needed. The angles above describe an approximate
15-degree outward arrangement; adjust them to match your placement if desired.

The dashboard now uses warm ivory, charcoal typography, fine architectural rules
and a terracotta position marker/path. Its floor plan, large **Distance from radar**
reading and two camera views share one light layout. Recording status stays in the
header; connection and waiting states use plain language. The design also applies
to the enlarged camera views and details panel. Press Q in the old window, then
restart to load it; the fresh filename above preserves earlier recordings.

The main marker and trail come only from the radar. The two camera panels show independent
detection boxes without asserting that their tracker IDs represent the same person.
With one radar detection, it appears once as the main marker rather than as a
second amber copy.

## 3. Check the coverage using the large camera views

| Key | Action |
| --- | --- |
| **V** | Enlarge both full camera views; press again to return to the map |
| **F** | Toggle fullscreen |
| **D** | Show details, source and connection status |
| **C** | Clear the path |
| **Q** | Save and close |

1. Press V and walk across the left, middle and right parts of the room.
2. Adjust camera angles until the useful walking area is visible in at least one
   view. A person visible in only one camera is sufficient for visual coverage.
3. Press V to return to the map. Walk the same route and check the radar position.
4. Cover one camera lens, then both briefly: the map should continue while radar
   reports continue. Detection boxes disappear when their view is obstructed.
5. Check a few tape-measured positions. Radar placement/orientation controls the
   room coordinates; camera calibration is irrelevant to them in this mode.

If the original camera images still show too little area, adjust their placement
and lens/zoom settings. An optional capture request is
`--capture-width 1280 --capture-height 720`, if both cameras support it; inspect
the actual field of view with V. Changing resolution alone is not a guarantee of
wider lens coverage. Different cameras can deliver different frame sizes here.

## 4. Keep the demo interpretable

- Use **one person** in the radar's view at first. With multiple detections, the
  dashboard shows them and waits for a single target instead of picking an arbitrary
  person and joining their paths. This is not cross-camera identity recognition.
- Fresh empty radar reports show no active position. Missing reports show a waiting
  state, with no old distance presented as current. Previously observed serial gaps
  can still affect this mode; camera images cannot replace missing radar positions.
- Sudden large radar jumps start a new path instead of drawing a misleading line.
- The room rectangle comes from measured dimensions. This is a live person-location
  display, with no automatic wall or furniture reconstruction.

Record a short walk left-to-right and toward/away from the sensors, then press Q.
The MP4 contains the dashboard; its same-name CSV contains radar position samples.
Choose a fresh filename for each take to preserve earlier recordings.

## Verification

64 targeted tests passed, including full original-frame camera input, radar
position with a camera disconnected and no calibration file, stale/multiple-target
handling, recorded CSV provenance, and existing stereo/geometry checks. Actual
wide-area walking and radar-placement checks remain the user's hardware tests.
