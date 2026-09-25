"""Base-station configuration. Override via env vars where useful.

Note on timing: these are dataclass field *defaults*, so every `os.getenv` here runs once
when this module is first imported, not when a `Config` is constructed. Set the env vars
before launching the process. Tests that need a different value should monkeypatch the
`CONFIG` singleton's attribute rather than the environment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_pose(name: str, default: tuple[float, float, float]) -> tuple[float, float, float]:
    """Parse 'x_m,y_m,yaw_deg' from an env var; fall back to `default` if unset/bad."""
    raw = os.getenv(name)
    if not raw:
        return default
    parts = [p for p in raw.replace(";", ",").split(",") if p.strip()]
    if len(parts) != 3:
        return default
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return default


@dataclass
class Config:
    # networking
    udp_port: int = int(os.getenv("KGN_UDP_PORT", "5005"))
    drone_ip: str = os.getenv("KGN_DRONE_IP", "192.168.4.2")

    # room geometry (metres). Origin at one corner; used to place nodes + clamp targets.
    room_w_m: float = float(os.getenv("KGN_ROOM_W", "4.0"))
    room_l_m: float = float(os.getenv("KGN_ROOM_L", "5.0"))

    # LD2450 node placements: node_id -> (x_m, y_m, yaw_deg) in the room frame.
    # TODO(kogane): set to the actual corner mounting once room dims are confirmed.
    node_poses: dict[int, tuple[float, float, float]] = field(default_factory=lambda: {
        0: (0.0, 0.0, 45.0),
        1: (4.0, 5.0, 225.0),
    })

    # follow behaviour
    follow_distance_m: float = 1.2
    max_speed_cms: int = 60          # clamp on commanded velocity
    kp_xy: float = 0.8               # position-error -> velocity gain

    # fusion
    process_noise: float = 0.5
    meas_noise: float = 0.3

    loop_hz: float = 30.0

    # ---- failsafe -------------------------------------------------------------
    # If no *real* measurement (mmWave or camera) arrives within this window the
    # control loop stops emitting VELOCITY setpoints and sends CtrlMode.HOLD instead.
    # The KF will happily dead-reckon forever; the drone's failsafe is DROP, so we
    # must not keep flying on extrapolated state.
    target_stale_s: float = float(os.getenv("KGN_TARGET_STALE_S", "1.0"))

    # ---- mmWave radar on a local serial port ----------------------------------
    # The BOM has one HLK-LD2450 plus a 3.3 V USB-UART adapter and no ESP32-C3, so the
    # radar is wired straight to this laptop: LD2450 -> USB-UART -> kogane_base. The
    # ESP32-C3 node firmware path (KGN MMWAVE_TARGETS datagrams) still works and needs no
    # config here; this block is only for the directly-attached module.
    #
    # Off by default: a run with no radar behaves exactly as before.
    radar_enabled: bool = _env_bool("KGN_RADAR", False)

    # Serial device. Windows "COM5", Linux "/dev/ttyUSB0", macOS "/dev/tty.usbserial-XXXX".
    # Any pyserial URL also works, which is how the radar path is exercised without a
    # module: "socket://127.0.0.1:5556" reads frames from a TCP feeder, "loop://" from an
    # in-process loopback.
    # Deliberately empty by default: guessing a port and opening someone else's device is
    # worse than logging the ports that do exist and carrying on without radar.
    radar_port: str = os.getenv("KGN_RADAR_PORT", "")
    radar_baud: int = int(os.getenv("KGN_RADAR_BAUD", "256000"))  # LD2450 factory default

    # Which `node_poses` entry to place the detections with. A directly-attached radar is
    # still "a node" as far as the room transform is concerned, so it reuses node 0's pose
    # rather than inventing a second coordinate convention. Point node 0 at wherever the
    # module is actually sitting (or override with KGN_RADAR_NODE_ID).
    radar_node_id: int = int(os.getenv("KGN_RADAR_NODE_ID", "0"))

    # ---- drone panel (SCREEN_FRAME 0x30) --------------------------------------
    # The live readout push is off by default and must stay that way: any non-STATUS
    # chunk takes the panel away from the drone's own status screen for 5 s, so a
    # background loop would fight a manual `kogane-screen --image ...` for the display.
    # Turn it on deliberately (KGN_SCREEN=1) when the readout is what you want to see.
    screen_enabled: bool = _env_bool("KGN_SCREEN", False)

    # "text"  -> 6 fmt=2 rows per update, ~6 datagrams. Cheap; the default.
    # "panel" -> a PIL-composed RGB565 frame, 120 datagrams per update. Needs Pillow.
    screen_mode: str = os.getenv("KGN_SCREEN_MODE", "text")
    screen_interval_s: float = float(os.getenv("KGN_SCREEN_INTERVAL_S", "1.0"))
    screen_text_scale: int = int(os.getenv("KGN_SCREEN_TEXT_SCALE", "2"))

    # Full-width strip height. 320 x 2 px = 1280 bytes, inside the 1440-byte tile budget;
    # 3 rows would be 1920 and the drone would drop every chunk.
    screen_strip_rows: int = int(os.getenv("KGN_SCREEN_STRIP_ROWS", "2"))

    # Gap between strips. The drone's display task is priority 3 with a queue depth of 4,
    # so a 120-chunk frame blasted at line rate loses strips to a full queue. 4 ms puts a
    # full frame at ~0.5 s, which the SPI blit and the task can both keep up with.
    screen_strip_delay_ms: float = float(os.getenv("KGN_SCREEN_STRIP_DELAY_MS", "4.0"))

    # ---- drone audio (AUDIO_TTS 0x40 / AUDIO_MIC 0x41) ------------------------
    # Chunk length for outbound PCM. 20 ms = 320 samples = 640 bytes, well inside the
    # 45 ms / 1440-byte cap, and small enough that the drone's 12-deep queue is a quarter
    # of a second of slack rather than half a second of latency.
    audio_chunk_ms: float = float(os.getenv("KGN_AUDIO_CHUNK_MS", "20.0"))

    # How far ahead of real time to run. The drone drops the OLDEST chunk on overflow, so
    # outrunning it by more than the queue holds eats the start of the utterance. A small
    # lead absorbs host scheduling jitter without risking that.
    audio_lead_ms: float = float(os.getenv("KGN_AUDIO_LEAD_MS", "120.0"))

    # SAPI voice name substring (empty = system default) and rate (-10..10, 0 = normal).
    tts_voice: str = os.getenv("KGN_TTS_VOICE", "")
    tts_rate: int = int(os.getenv("KGN_TTS_RATE", "0"))

    # Where to dump AUDIO_MIC audio the base station receives. Empty = keep nothing.
    # The mic is off on the drone until something sends CTRL MIC_ON, so this being set
    # does not by itself start a recording.
    mic_wav_path: str = os.getenv("KGN_MIC_WAV", "")
    mic_max_seconds: float = float(os.getenv("KGN_MIC_MAX_S", "300.0"))

    # ---- vision ---------------------------------------------------------------
    # Off by default: a headless run with no camera behaves exactly as before.
    vision_enabled: bool = _env_bool("KGN_VISION", False)

    # source: kind is one of webcam | usb | video | mjpeg (see vision.sources.make_source),
    # value is the camera index, file path, or stream URL.
    camera_kind: str = os.getenv("KGN_CAM_KIND", "webcam")
    camera_value: str = os.getenv("KGN_CAM_VALUE", "0")

    cv_model_path: str = os.getenv("KGN_CV_MODEL", "yolov8n.pt")
    cv_device: str = os.getenv("KGN_CV_DEVICE", "cpu")     # cpu | 0 (cuda:0) | mps
    cv_conf: float = float(os.getenv("KGN_CV_CONF", "0.35"))
    cv_tracker: str = os.getenv("KGN_CV_TRACKER", "bytetrack.yaml")

    # monocular geometry
    cam_hfov_deg: float = float(os.getenv("KGN_CAM_HFOV", "70.0"))
    assumed_person_height_m: float = float(os.getenv("KGN_PERSON_H", "1.7"))

    # Where the camera sits in the room frame: (x_m, y_m, yaw_deg).
    # Same rotation convention as node_poses / tracking.mmwave.node_frame_to_room:
    # the sensor's own frame is +x right, +y forward, and yaw rotates that frame into the
    # room frame as (rx, ry) = (x*cos - y*sin, x*sin + y*cos). So yaw=0 means the camera
    # looks along room +y, yaw=90 means it looks along room -x, yaw=-90 along room +x.
    # Default: camera at the origin corner looking into the room along +y.
    cam_pose: tuple[float, float, float] = _env_pose("KGN_CAM_POSE", (0.0, 0.0, 0.0))

    # Fixed room camera only: a calibrated floor-plane homography beats height-based
    # distance by a wide margin. If this file exists AND the flag is on, it is used;
    # otherwise we fall back to MonocularEstimator. See vision/geometry.py.
    floor_calib_path: str = os.getenv("KGN_FLOOR_CALIB", "calib/floor_homography.json")
    use_floor_homography: bool = _env_bool("KGN_USE_FLOOR_HOMOGRAPHY", False)

    # ---- pose ----------------------------------------------------------------
    # Independently toggleable: a second inference pass costs real time on CPU.
    pose_enabled: bool = _env_bool("KGN_POSE", False)
    pose_model_path: str = os.getenv("KGN_POSE_MODEL", "yolov8n-pose.pt")
    pose_conf: float = float(os.getenv("KGN_POSE_CONF", "0.35"))

    # ---- FaceID --------------------------------------------------------------
    faceid_enabled: bool = _env_bool("KGN_FACEID", False)
    face_detect_model: str = os.getenv(
        "KGN_FACE_DET_MODEL", "models/face_detection_yunet_2023mar.onnx")
    face_recog_model: str = os.getenv(
        "KGN_FACE_REC_MODEL", "models/face_recognition_sface_2021dec.onnx")
    face_db_path: str = os.getenv("KGN_FACE_DB", "models/face_db.json")
    # SFace cosine-similarity threshold. 0.363 is the value OpenCV's own face-match
    # sample uses for "same identity"; raise it to be stricter.
    face_match_threshold: float = float(os.getenv("KGN_FACE_THRESHOLD", "0.363"))
    face_score_threshold: float = float(os.getenv("KGN_FACE_SCORE", "0.8"))
    # Run FaceID every Nth frame only — it is far cheaper than YOLO but not free.
    face_every_n_frames: int = int(os.getenv("KGN_FACE_EVERY_N", "5"))


CONFIG = Config()
