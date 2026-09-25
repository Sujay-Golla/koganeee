# KOGANE Base Station (laptop, Python)

The off-board brain. Fuses mmWave (+ camera) into a smooth target position, runs the voice
pipeline, streams UI to the drone screen, and sends velocity/position **setpoints** to the
drone over Wi-Fi UDP (which the ESP32 turns into MSP override for iNAV).

## Modules
| Module | File | Role |
|--------|------|------|
| Net | `kogane_base/net/udp.py` | async UDP endpoint, `KGN` pack/unpack |
| Protocol | `kogane_base/protocol.py` | Python mirror of `shared/PROTOCOL.md` |
| mmWave | `kogane_base/tracking/mmwave.py` | ingest node datagrams -> raw detections |
| LD2450 decode | `kogane_base/tracking/ld2450.py` | pure streaming parser for the radar's UART frames |
| LD2450 serial | `kogane_base/tracking/radar.py` | owns the serial port, feeds the same room frame |
| mmWave sim | `kogane_base/tools/mmwave_sim.py` | fake walking person over UDP, no radar needed |
| Fusion | `kogane_base/fusion/kalman.py` | constant-velocity Kalman -> (x, y, heading) |
| Setpoints | `kogane_base/link/setpoint.py` | position error -> velocity setpoint -> drone |
| Failsafe | `kogane_base/link/failsafe.py` | measurement-staleness state machine (VELOCITY vs HOLD) |
| Vision | `kogane_base/vision/` | camera -> person tracking -> room-frame position (see below) |
| Voice | `kogane_base/voice/pipeline.py` | wakeword -> STT -> LLM -> TTS (stubs) |
| Screen | `kogane_base/screen/renderer.py` | render UI frames, stream to drone display |
| Orchestrator | `kogane_base/main.py` | wires everything, runs the async loop |

## Run
```powershell
cd firmware/base-station
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e .
python -m kogane_base        # starts UDP server + fusion + setpoint loop (voice/screen stubbed)
```

## Config
Edit `kogane_base/config.py` (or set env vars): UDP port, drone IP, room geometry, node corner
positions, follow distance, control gains. Corner placement of the two LD2450 nodes must match
`NODE_ID` in the node firmware so detections land in the right room frame.

## mmWave: two paths to the same room frame

The BOM has one HLK-LD2450 and a 3.3 V USB-UART adapter, and **no ESP32-C3**. So the path
that actually has parts is `LD2450 -> USB-UART -> this laptop`, and the laptop parses the
radar's own UART protocol. The ESP32-C3 node firmware in `firmware/mmwave-node-esp32c3/`
still works if boards are ever bought; both paths end in the same two calls.

| | node path | direct path |
|---|---|---|
| Transport | Wi-Fi, `KGN MMWAVE_TARGETS` datagram | USB-UART, raw LD2450 frames |
| Decoder | `protocol.parse_mmwave` | `tracking/ld2450.py` |
| Entry point | `BaseStation._on_frame` | `BaseStation._on_radar` |
| Room transform | `node_frame_to_room` | `node_frame_to_room` |

```powershell
pip install -e .[radar]              # adds pyserial only
$env:KGN_RADAR=1; $env:KGN_RADAR_PORT="COM5"   # 256000 baud by default
python -m kogane_base
```

Radar env vars: `KGN_RADAR`, `KGN_RADAR_PORT`, `KGN_RADAR_BAUD`, `KGN_RADAR_NODE_ID`.
`KGN_RADAR_NODE_ID` (default `0`) selects which `CONFIG.node_poses` entry places the
detections, so point node 0's pose at wherever the module physically sits. Read once at
import time, like every other setting here.

The serial read runs on a worker thread via `asyncio.to_thread` and hands results back with
`loop.call_soon_threadsafe`, exactly like `vision/runner.py`, so the 30 Hz control loop never
waits on a 256000-baud read. Missing pyserial, an unset port, a busy port, a mid-run unplug
and pure noise all log and degrade to "radar off" — they never take the base station down.

`KGN_RADAR_PORT` accepts any pyserial URL, so the whole read path can be exercised with no
hardware: point it at `socket://127.0.0.1:5556` and stream `ld2450.encode_report(...)` bytes
from a TCP server.

### Sign encoding, the one trap
LD2450 coordinates and speed are **sign-magnitude**: bit 15 is a sign flag (set = positive)
and the low 15 bits are the magnitude. Reading the field as a little-endian `int16` mirrors
every target about the boresight. `ld2450.decode_signed` is the single place this is handled;
its polarity follows ESPHome's `ld2450` component and the C mirror in `mmwave-node-esp32c3`.
It has **not** been checked against bytes from a physical module.

## Demo it with no radar and no drone
```powershell
python -m kogane_base                    # terminal 1
kogane-mmwave-sim --path circle --fake-drone   # terminal 2
```
`kogane-mmwave-sim` synthesises a person walking a configurable path and sends real
`MMWAVE_TARGETS` datagrams, which is what makes fusion -> failsafe -> setpoints observable on
video. The path is defined in room metres and converted into the chosen node's sensor frame,
so a wrong `node_poses` entry shows up immediately. `--fake-drone` also sends one HEARTBEAT so
the base addresses its setpoints back to the simulator, and prints them as they arrive.

```powershell
kogane-mmwave-sim --path line --length 3 --speed 0.8 --rate 10
kogane-mmwave-sim --path square --node-id 1 --center 2,2.5
kogane-mmwave-sim --path circle --drop 0.6        # provoke the staleness failsafe
```

## Safety: the staleness failsafe
The Kalman filter dead-reckons indefinitely once seeded, so a lost target would otherwise
produce confident-looking setpoints forever. The drone's failsafe is **DROP**, so that is
dangerous. `link/failsafe.py` tracks the newest *real* measurement from either sensor; if
nothing arrives within `target_stale_s` (default 1.0 s) the control loop stops sending
`VELOCITY` and sends `CtrlMode.HOLD` instead, logging the transition once. It resumes
following only when a genuine measurement arrives.

Freshness is measured from the frame's **capture** time, not from when inference finished,
so a slow inference pass correctly counts against the budget. One consequence worth knowing:
the very first frame after startup often lands stale, because the first YOLO pass includes
model warm-up (~1.2 s on CPU). The loop holds, then starts following on the next frame.

## Status
Networking, protocol, mmWave ingest (both the node datagram path and a directly-attached
LD2450 over USB-UART), the Kalman filter, the P-controller setpoint loop, the staleness
failsafe and the full vision path (detection, tracking, room-frame projection, pose/gesture,
FaceID) are functional. Voice and screen are stubbed (`TODO(kogane)`), ready for
openWakeWord / Deepgram / Claude / ElevenLabs and the screen renderer.

Run the tests with `python -m pytest` (304 tests, no camera, radar or network needed).

---

## Computer vision (testable now, no drone needed)

`kogane_base/vision/` runs **person detection + tracking on the laptop webcam** — the fastest
way to validate the CV path before the drone camera exists.

```powershell
cd firmware/base-station
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e .[vision]          # opencv-python + ultralytics (YOLOv8n auto-downloads)

kogane-cv                          # webcam, live window with boxes + tracked ids
python -m kogane_base.vision.demo --source webcam --fuse   # also run the Kalman filter
python -m kogane_base.vision.demo --source video  --path clip.mp4
python -m kogane_base.vision.demo --source mjpeg  --url http://<drone-ip>/stream
python -m kogane_base.vision.demo --headless       # no window, prints target position

python -m kogane_base.vision.demo --pose                   # + skeleton and arm-raise gesture
python -m kogane_base.vision.demo --faceid                 # + name known faces
python -m kogane_base.vision.demo --faceid --enroll NAME    # press 'e' to enroll a face
python -m kogane_base.vision.demo --faceid --face-lock      # a known face takes the lock
python -m kogane_base.vision.demo --faceid --list-faces     # who is enrolled, then exit
python -m kogane_base.vision.demo --homography calib/floor.json   # calibrated room metres
```
Window keys: `q` quit, `l` lock/unlock onto the current primary target, `e` enroll a face.

### What it does
| File | Role |
|------|------|
| `vision/sources.py` | webcam / video-file / MJPEG-stream frame sources (OpenCV) |
| `vision/detector.py` | YOLOv8n person detection + ByteTrack ids; `select_primary()` picks who to follow |
| `vision/geometry.py` | bbox → room-frame metres, two ways: monocular pinhole or floor homography |
| `vision/pose.py` | yolov8n-pose COCO-17 keypoints + pure gesture predicates |
| `vision/faceid.py` | YuNet detection + SFace embeddings + persistent JSON face DB |
| `vision/models.py` | resolves/downloads the YuNet & SFace ONNX weights |
| `vision/runner.py` | runs capture+inference off the event loop, feeds `BaseStation` |
| `vision/calibrate.py` | click 4+ floor points to build the homography |
| `vision/demo.py` | the runnable test harness (draw, FPS, `--fuse`, `--pose`, `--faceid`) |

### Wired into the base station
Vision is off by default. Turn it on with `KGN_VISION=1` and `python -m kogane_base`:
capture and inference run on a worker thread via `asyncio.to_thread`, and results are handed
back to the event loop with `loop.call_soon_threadsafe`, so the 30 Hz control loop is never
blocked by a ~90 ms inference pass. Camera estimates land in the **same room frame** as
`tracking/mmwave.py`, so a camera detection is just another `PositionFilter.update(x, y)`.
A camera that won't open, a stream that drops, or a missing model all degrade to "vision off"
rather than taking the base station down.

### Choosing a distance method (explicit, not automatic)
| | `MonocularEstimator` | `FloorHomography` |
|---|---|---|
| Needs calibration | no | yes, 4+ floor points |
| Camera may move | **yes** | no, fixed only |
| Accuracy | ±20–40% on range | cm-class if measured well |
| Fails when | person is short/tall or top-cropped | feet not visible |
| Use for | **the drone's own camera** | **the fixed room camera** |

`RoomProjector.from_monocular(...)` / `.from_homography(...)` makes the choice explicit and
records it in `RoomFix.method`, so logs always say how a position was derived. Calibrate with:
```powershell
python -m kogane_base.vision.calibrate --source webcam --out calib/floor.json
# or non-interactively, if you already measured:
python -m kogane_base.vision.calibrate --points "60,470=-1.5,1.0; 580,470=1.5,1.0; 430,250=1.5,6.0; 210,250=-1.5,6.0"
$env:KGN_USE_FLOOR_HOMOGRAPHY=1; $env:KGN_FLOOR_CALIB="calib/floor.json"
```
Aim for a reported reprojection error under ~0.10 m; higher means a mis-measured point.

### Pose and FaceID add no new pip dependencies
- **Pose** uses ultralytics' own `yolov8n-pose.pt` (auto-downloads, ~6.5 MB) rather than
  mediapipe. The gesture logic (`classify_gesture`, `is_arm_raised`, `BeckonDetector`) is pure
  functions over a `(17, 3)` keypoint array, so it is unit-tested without a camera. Thresholds
  are a fraction of torso length, so they hold at any distance. Costs roughly half your frame
  rate on CPU, hence the separate `KGN_POSE` toggle.
- **FaceID** uses `cv2.FaceDetectorYN` (YuNet) and `cv2.FaceRecognizerSF` (SFace, 128-D), which
  ship inside opencv itself — no dlib, no mediapipe. The two ONNX weight files are fetched from
  the [OpenCV Model Zoo](https://github.com/opencv/opencv_zoo) (Apache-2.0) into `models/` on
  first use; a missing file raises a clear error with manual instructions. A recognised face
  sets the tracker's `locked_id`, so the drone keeps following *you* even when someone else is
  closer to the camera.

**Privacy:** `models/face_db.json` holds face embeddings, which are biometric personal data.
It is git-ignored. Don't commit it, and get consent before enrolling anyone.

### Accuracy notes
- **Bearing** (left/right angle) is reliable. Monocular **distance** is estimated from apparent
  person height (assumes ~1.7 m, tune with `--person-height`) — rough, fine for testing
  "closer = bigger" and the loop. Set `--hfov` to your camera's real horizontal FOV.
- SFace's cosine threshold defaults to 0.363 (OpenCV's own value for "same person"). Raise
  `KGN_FACE_THRESHOLD` to be stricter. Don't set it to 1.0 — float cosine never quite reaches it.

### Vision env vars
`KGN_VISION`, `KGN_POSE`, `KGN_FACEID`, `KGN_CAM_KIND`, `KGN_CAM_VALUE`, `KGN_CV_MODEL`,
`KGN_CV_DEVICE`, `KGN_CV_CONF`, `KGN_CAM_HFOV`, `KGN_PERSON_H`, `KGN_CAM_POSE` (`x,y,yaw_deg`),
`KGN_USE_FLOOR_HOMOGRAPHY`, `KGN_FLOOR_CALIB`, `KGN_POSE_MODEL`, `KGN_FACE_DB`,
`KGN_FACE_THRESHOLD`, `KGN_FACE_EVERY_N`, `KGN_TARGET_STALE_S`. These are read **once at
import time**, so set them before launching.
