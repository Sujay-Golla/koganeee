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
| Fusion | `kogane_base/fusion/kalman.py` | constant-velocity Kalman -> (x, y, heading) |
| Setpoints | `kogane_base/link/setpoint.py` | position error -> velocity setpoint -> drone |
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

## Status
Networking, protocol, mmWave ingest, a working Kalman filter, and a P-controller setpoint loop
are functional in skeleton form. Voice and screen are stubbed (`TODO(kogane)`), ready for
openWakeWord / Deepgram / Claude / ElevenLabs and the screen renderer.

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
```
Window keys: `q` quit, `l` lock/unlock onto the current primary target.

### What it does
| File | Role |
|------|------|
| `vision/sources.py` | webcam / video-file / MJPEG-stream frame sources (OpenCV) |
| `vision/detector.py` | YOLOv8n person detection + ByteTrack ids; `select_primary()` picks who to follow |
| `vision/geometry.py` | monocular bbox → bearing + rough distance → camera-frame (x, y) |
| `vision/demo.py` | the runnable test harness (draw, FPS, optional `--fuse`) |

### How it plugs into the rest later
`MonocularEstimator.estimate()` → `project_to_room()` produces a room-frame (x, y) in the
**same coordinate frame** as `tracking/mmwave.py`, so a camera detection is just another
`PositionFilter.update(x, y)` measurement. `--fuse` already demonstrates this on one target.

### Accuracy notes
- **Bearing** (left/right angle) is reliable. **Distance** is estimated from apparent person
  height (assumes ~1.7 m) — rough (±20–40%), fine for testing "closer = bigger" and the loop.
- For the **fixed room camera**, swap height-based distance for a floor-plane homography
  (4 clicked floor points) — marked `TODO(kogane)` in `geometry.py::project_to_room`.
- Set `--hfov` to your camera's real horizontal FOV for better numbers.
