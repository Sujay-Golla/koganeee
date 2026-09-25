"""Bridge the blocking camera/inference loop into the asyncio base station.

Why a thread at all: `cv2.VideoCapture.read()` blocks, and a YOLOv8n forward pass on CPU
takes tens of milliseconds. Either one, run inline, would stall the 30 Hz control loop
that shares the event loop. So the capture+inference loop runs via `asyncio.to_thread`
and hands finished observations back with `loop.call_soon_threadsafe`, which means the
callback executes on the event loop thread — the same thread as `_control_loop` and
`_on_frame` — so no locking is needed around the filter.

Everything here degrades instead of raising: a camera that will not open, a stream that
drops mid-run, a missing FaceID model, an ultralytics import failure. The base station
must keep flying (or keep safely holding) regardless.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

from ..config import CONFIG

log = logging.getLogger("kogane.vision.runner")

# How hard to try to (re)open the camera before giving up on vision for this run.
_OPEN_RETRIES = 3
_OPEN_BACKOFF_S = 2.0
# Consecutive failed reads before we tear the source down and reopen it.
_READ_FAIL_LIMIT = 30
_REOPEN_LIMIT = 3


@dataclass
class VisionObservation:
    """One camera measurement, already in the shared room frame."""
    t_mono: float
    x_m: float
    y_m: float
    conf: float
    method: str                      # "homography" | "monocular"
    track_id: int
    distance_m: float | None = None
    bearing_deg: float | None = None
    identity: str | None = None      # recognised face name, if any
    gesture: str = "-"               # human-readable gesture label
    beckon: bool = False             # rising edge of the 'come here' gesture
    fps: float = 0.0


class VisionWorker:
    """Owns the camera, the models, and the lock-on state.

    Construct it always; it is inert unless `CONFIG.vision_enabled`. All model objects
    are built inside the worker thread, so nothing heavy is imported or loaded on a
    headless run.
    """

    def __init__(self, on_observation=None, cfg=None) -> None:
        self.cfg = cfg or CONFIG
        self._cb = on_observation
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

        # observable state, for the screen renderer / logs
        self.fps = 0.0
        self.locked_id: int | None = None
        self.locked_name: str | None = None
        self.active = False
        self.last_error: str | None = None
        self.frames_seen = 0

    # ---- lifecycle ----
    async def run(self) -> None:
        """Task body for `asyncio.gather`. Returns immediately when vision is off."""
        if not self.cfg.vision_enabled:
            log.info("vision disabled (set KGN_VISION=1 to enable) — no camera opened")
            return
        self._loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(self._worker)
        except asyncio.CancelledError:
            # to_thread cannot be interrupted; ask the loop to finish its current frame.
            self._stop.set()
            raise
        finally:
            self.active = False
        log.info("vision task exited after %d frames", self.frames_seen)

    def stop(self) -> None:
        self._stop.set()

    # ---- thread -> event loop ----
    def _emit(self, obs: VisionObservation) -> None:
        if self._cb is None:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._cb, obs)
        except RuntimeError:
            pass  # loop shut down between the check and the call

    # ---- model construction (inside the worker thread) ----
    def _build_detector(self):
        from .detector import PersonDetector

        log.info("loading detector %s on %s", self.cfg.cv_model_path, self.cfg.cv_device)
        return PersonDetector(self.cfg.cv_model_path, device=self.cfg.cv_device,
                              conf=self.cfg.cv_conf, tracker=self.cfg.cv_tracker)

    def _build_pose(self):
        if not self.cfg.pose_enabled:
            return None
        try:
            from .pose import PoseEstimator

            log.info("loading pose model %s", self.cfg.pose_model_path)
            return PoseEstimator(self.cfg.pose_model_path, device=self.cfg.cv_device,
                                 conf=self.cfg.pose_conf)
        except Exception as e:
            log.error("pose disabled — could not load %s: %s", self.cfg.pose_model_path, e)
            return None

    def _build_faceid(self):
        if not self.cfg.faceid_enabled:
            return None
        try:
            from .faceid import try_build_identifier

            fid = try_build_identifier(self.cfg)
            if fid is not None:
                log.info("FaceID ready; enrolled: %s", fid.db.names or "(nobody)")
            return fid
        except Exception as e:
            log.error("FaceID disabled — %s", e)
            return None

    def _build_projector(self, w: int, h: int):
        """Choose the room-frame projection method explicitly, and say which was chosen."""
        from .geometry import (FloorHomography, FloorHomographyError, MonocularEstimator,
                               RoomProjector)

        if self.cfg.use_floor_homography:
            try:
                hom = FloorHomography.load(self.cfg.floor_calib_path)
                err = hom.reprojection_error_m()
                log.info("using floor homography from %s (reprojection error %s)",
                         self.cfg.floor_calib_path,
                         "unknown" if err is None else f"{err:.3f} m")
                return RoomProjector.from_homography(hom)
            except FloorHomographyError as e:
                log.warning("floor homography unavailable, falling back to monocular "
                            "height-based distance: %s", e)

        est = MonocularEstimator(w, h, hfov_deg=self.cfg.cam_hfov_deg,
                                 assumed_person_height_m=self.cfg.assumed_person_height_m)
        log.info("using monocular estimator (hfov=%.0fdeg, person_h=%.2fm, cam_pose=%s)",
                 self.cfg.cam_hfov_deg, self.cfg.assumed_person_height_m, self.cfg.cam_pose)
        return RoomProjector.from_monocular(est, tuple(self.cfg.cam_pose))

    # ---- source handling ----
    def _open_source(self):
        """Open the configured source, retrying with backoff. None => give up."""
        from .sources import make_source

        for attempt in range(1, _OPEN_RETRIES + 1):
            if self._stop.is_set():
                return None
            try:
                src = make_source(self.cfg.camera_kind, self.cfg.camera_value)
                log.info("camera open: kind=%s value=%r size=%s",
                         self.cfg.camera_kind, self.cfg.camera_value, src.size)
                return src
            except Exception as e:
                self.last_error = f"camera open failed: {e}"
                log.error("camera open attempt %d/%d failed (%s=%r): %s",
                          attempt, _OPEN_RETRIES, self.cfg.camera_kind,
                          self.cfg.camera_value, e)
                if attempt < _OPEN_RETRIES:
                    self._stop.wait(_OPEN_BACKOFF_S)
        log.error("giving up on vision: could not open camera after %d attempts. "
                  "The base station continues without it.", _OPEN_RETRIES)
        return None

    def _frame_size(self, src) -> tuple[int, int]:
        try:
            w, h = src.size
        except Exception:
            w, h = 0, 0
        return (w, h) if w and h else (0, 0)

    # ---- the blocking loop ----
    def _worker(self) -> None:
        try:
            detector = self._build_detector()
        except Exception as e:
            self.last_error = f"detector load failed: {e}"
            log.error("vision disabled — could not load the detector (%s). Install the "
                      "vision extra with `pip install -e .[vision]`.", e)
            return

        pose = self._build_pose()
        faceid = self._build_faceid()
        beckon = None
        if pose is not None:
            from .pose import BeckonDetector

            beckon = BeckonDetector()

        reopens = 0
        while not self._stop.is_set():
            src = self._open_source()
            if src is None:
                return
            try:
                clean_exit = self._read_loop(src, detector, pose, faceid, beckon)
            finally:
                try:
                    src.release()
                except Exception:
                    pass
                self.active = False
            if clean_exit or self._stop.is_set():
                return                      # video file ended, or we were asked to stop
            reopens += 1
            if reopens > _REOPEN_LIMIT:
                log.error("vision giving up after %d reopen attempts; base station "
                          "continues without camera input", reopens)
                return
            log.warning("reopening camera (attempt %d/%d)", reopens, _REOPEN_LIMIT)
            self._stop.wait(_OPEN_BACKOFF_S)

    def _read_loop(self, src, detector, pose, faceid, beckon) -> bool:
        """Read/infer until stopped or the source dies. True => source ended cleanly."""
        from .detector import select_primary

        w, h = self._frame_size(src)
        projector = None
        read_fails = 0
        last_t = time.monotonic()
        frame_i = 0
        faces: list = []

        while not self._stop.is_set():
            try:
                frame = next(iter(src))
            except StopIteration:
                # FrameSource raises StopIteration whenever cv2 read() returns False.
                # For a file that means end-of-clip (a clean exit). For a live camera or
                # stream it means the device or connection died, which should be retried.
                if self.cfg.camera_kind == "video":
                    log.info("video source ended after %d frames", frame_i)
                    return True
                read_fails += 1
                self.last_error = "frame read returned no image (camera or stream lost?)"
                if read_fails == 1 or read_fails % 10 == 0:
                    log.warning("empty read from %s source (%d consecutive)",
                                self.cfg.camera_kind, read_fails)
                if read_fails >= _READ_FAIL_LIMIT:
                    log.error("%d consecutive empty reads — dropping the source", read_fails)
                    return False
                self._stop.wait(0.05)
                continue
            except Exception as e:
                read_fails += 1
                self.last_error = f"frame read failed: {e}"
                if read_fails == 1 or read_fails % 10 == 0:
                    log.warning("frame read failed (%d consecutive): %s", read_fails, e)
                if read_fails >= _READ_FAIL_LIMIT:
                    log.error("%d consecutive read failures — dropping the source",
                              read_fails)
                    return False
                self._stop.wait(0.05)
                continue

            read_fails = 0
            frame_i += 1
            self.frames_seen += 1
            self.active = True

            if projector is None:
                if not (w and h):
                    h, w = frame.image.shape[:2]
                projector = self._build_projector(w, h)

            now = time.monotonic()
            dt = max(1e-3, now - last_t)
            last_t = now
            self.fps = (0.9 * self.fps + 0.1 / dt) if self.fps else 1.0 / dt

            try:
                tracks = detector.track(frame.image)
            except Exception as e:
                self.last_error = f"inference failed: {e}"
                log.warning("detector.track failed on frame %d: %s", frame_i, e)
                continue

            # --- FaceID: may move the lock onto a known person ---
            if faceid is not None and frame_i % max(1, self.cfg.face_every_n_frames) == 0:
                try:
                    from .faceid import resolve_locked_id

                    faces = faceid.identify_frame(frame.image)
                    new_id = resolve_locked_id(faces, tracks)
                    if new_id is not None and new_id != self.locked_id:
                        named = [f.ident.name for f in faces if f.ident.known]
                        self.locked_name = named[0] if named else None
                        self.locked_id = new_id
                        log.info("FaceID lock -> track %d (%s)", new_id, self.locked_name)
                except Exception as e:
                    log.warning("FaceID pass failed on frame %d: %s", frame_i, e)
                    faces = []

            primary = select_primary(tracks, self.locked_id)
            if primary is None:
                if beckon is not None:
                    beckon.update(False)
                continue

            # --- pose / gesture on the primary target only ---
            gesture_label, fired = "-", False
            if pose is not None:
                try:
                    from .pose import classify_gesture, match_pose_to_track

                    matched = match_pose_to_track(primary, pose.estimate(frame.image))
                    if matched is not None:
                        g = classify_gesture(matched.keypoints)
                        gesture_label = g.label
                        fired = beckon.update(g.any_arm_raised) if beckon else False
                        if fired:
                            log.info("beckon gesture from track %d — 'come here'",
                                     primary.track_id)
                    elif beckon is not None:
                        beckon.update(False)
                except Exception as e:
                    log.warning("pose pass failed on frame %d: %s", frame_i, e)

            try:
                fix = projector.locate(primary)
            except Exception as e:
                log.warning("room projection failed for track %d: %s",
                            primary.track_id, e)
                continue

            identity = self.locked_name if primary.track_id == self.locked_id else None
            self._emit(VisionObservation(
                t_mono=frame.t_mono, x_m=fix.x_m, y_m=fix.y_m, conf=fix.conf,
                method=fix.method, track_id=primary.track_id,
                distance_m=fix.distance_m, bearing_deg=fix.bearing_deg,
                identity=identity, gesture=gesture_label, beckon=fired, fps=self.fps))
        return False
