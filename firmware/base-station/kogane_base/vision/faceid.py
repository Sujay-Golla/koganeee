"""FaceID on OpenCV's built-in DNN face stack — no mediapipe, no dlib.

Verified against opencv-python 5.0.0 on this machine:
  * `cv2.FaceDetectorYN.create(...)`  -> `.detect(img)` returns `(rc, faces)` where
    `faces` is an (N, 15) float array: x, y, w, h, then 5 landmark xy pairs, then score.
  * `cv2.FaceRecognizerSF.create(...)` -> `.alignCrop(img, face_row)` gives a
    (112, 112, 3) uint8 crop and `.feature(crop)` gives a (1, 128) float32 embedding.
Both were exercised on a real photograph (2 faces found, 128-D embedding produced).

The weights are not bundled with opencv; see `models.py` for the pinned filenames and
their Model Zoo source. A missing model raises `ModelMissingError` with instructions
rather than failing deep inside the ONNX importer.

Split, so the interesting logic is testable without opencv or a camera:
  * `cosine_similarity`, `best_match`, `assign_face_to_track`, `resolve_locked_id`
    are pure functions over numpy arrays.
  * `FaceDB` is plain JSON I/O.
  * `FaceIdentifier` is the only class that touches cv2.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import numpy as np

from .models import ModelMissingError, ensure_model

log = logging.getLogger("kogane.vision.faceid")

EMBEDDING_DIM = 128            # SFace output width, confirmed by smoke test
DEFAULT_THRESHOLD = 0.363      # OpenCV's own SFace cosine threshold for "same person"


# --------------------------------------------------------------------------------------
# pure similarity / matching logic
# --------------------------------------------------------------------------------------

def cosine_similarity(a, b) -> float:
    """Cosine similarity of two embeddings, in [-1, 1]. Zero vectors give 0.0.

    Pure function. SFace embeddings are not unit-norm, so the division matters.
    """
    va = np.asarray(a, dtype=np.float64).ravel()
    vb = np.asarray(b, dtype=np.float64).ravel()
    if va.shape != vb.shape:
        raise ValueError(f"embedding shape mismatch: {va.shape} vs {vb.shape}")
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


@dataclass
class Identification:
    name: str | None          # None => below threshold, i.e. unknown
    score: float              # best similarity seen, even when rejected
    runner_up: float = 0.0    # best score among *other* people; a small gap means doubt

    @property
    def known(self) -> bool:
        return self.name is not None

    @property
    def margin(self) -> float:
        return self.score - self.runner_up


def best_match(embedding, people: dict[str, list],
               threshold: float = DEFAULT_THRESHOLD) -> Identification:
    """Nearest identity by cosine similarity, rejected if it fails `threshold`.

    `people` maps name -> list of embeddings (several per person is better: different
    lighting and head angles). A person's score is the best of their embeddings.
    Pure function, unit-tested on synthetic vectors.
    """
    if not people:
        return Identification(None, 0.0)
    per_person: list[tuple[str, float]] = []
    for name, embs in people.items():
        if not embs:
            continue
        per_person.append((name, max(cosine_similarity(embedding, e) for e in embs)))
    if not per_person:
        return Identification(None, 0.0)
    per_person.sort(key=lambda kv: kv[1], reverse=True)
    name, score = per_person[0]
    runner_up = per_person[1][1] if len(per_person) > 1 else 0.0
    if score < threshold:
        return Identification(None, score, runner_up)
    return Identification(name, score, runner_up)


def assign_face_to_track(face_box: tuple[float, float, float, float], tracks):
    """Which person track does a face box belong to? Pure function.

    A face is a small box inside a person box, so IoU is the wrong tool. We test whether
    the face centre falls inside the person box and, among those that contain it, take
    the smallest — that resolves the common case of one person standing in front of
    another, where the nearer (larger) box also contains the farther person's face.
    """
    fx1, fy1, fx2, fy2 = face_box
    fcx, fcy = (fx1 + fx2) / 2.0, (fy1 + fy2) / 2.0
    best, best_area = None, float("inf")
    for t in tracks:
        if t.x1 <= fcx <= t.x2 and t.y1 <= fcy <= t.y2:
            area = (t.x2 - t.x1) * (t.y2 - t.y1)
            if area < best_area:
                best, best_area = t, area
    return best


@dataclass
class FaceObservation:
    """One detected face in one frame, with whatever identity we could attach."""
    x1: float
    y1: float
    x2: float
    y2: float
    det_score: float
    ident: Identification = field(default_factory=lambda: Identification(None, 0.0))
    embedding: np.ndarray | None = None

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def label(self) -> str:
        if self.ident.known:
            return f"{self.ident.name} {self.ident.score:.2f}"
        return f"unknown {self.ident.score:.2f}"


def resolve_locked_id(faces: list[FaceObservation], tracks,
                      prefer: set[str] | None = None) -> int | None:
    """Turn recognised faces into the person track id to lock onto.

    This is the extension point `detector.select_primary`'s docstring anticipates: pass
    the result in as `locked_id` and the follow loop commits to that person even when
    someone else is closer to the camera.

    `prefer` optionally restricts to specific enrolled names (e.g. only the pilot).
    Highest-similarity recognised face wins. Pure function.
    """
    best_id, best_score = None, -1.0
    for f in faces:
        if not f.ident.known:
            continue
        if prefer and f.ident.name not in prefer:
            continue
        t = assign_face_to_track(f.box, tracks)
        if t is None or t.track_id < 0:
            continue
        if f.ident.score > best_score:
            best_id, best_score = t.track_id, f.ident.score
    return best_id


# --------------------------------------------------------------------------------------
# persistent face database
# --------------------------------------------------------------------------------------

class FaceDB:
    """JSON-backed name -> [embedding, ...] store.

    JSON rather than npz: a few 128-float vectors are tiny, and being able to open the
    file and see who is enrolled is worth more than the bytes saved.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.people: dict[str, list[np.ndarray]] = {}

    # ---- io ----
    def load(self) -> "FaceDB":
        """Load if present. A missing file is normal (nobody enrolled yet), not an error."""
        if not os.path.exists(self.path):
            log.info("no face DB at %s yet — enroll someone with `--enroll NAME`", self.path)
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            log.error("face DB %s is unreadable (%s); starting empty", self.path, e)
            return self
        people = raw.get("people", {})
        loaded = 0
        for name, embs in people.items():
            vecs = []
            for e in embs:
                v = np.asarray(e, dtype=np.float32).ravel()
                if v.size != EMBEDDING_DIM:
                    log.warning("skipping %s embedding of width %d (expected %d)",
                                name, v.size, EMBEDDING_DIM)
                    continue
                vecs.append(v)
            if vecs:
                self.people[name] = vecs
                loaded += len(vecs)
        log.info("face DB: %d people, %d embeddings from %s",
                 len(self.people), loaded, self.path)
        return self

    def save(self) -> None:
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        payload = {
            "type": "kogane.face_db",
            "version": 1,
            "dim": EMBEDDING_DIM,
            "model": "face_recognition_sface_2021dec",
            "people": {n: [v.tolist() for v in vs] for n, vs in self.people.items()},
        }
        tmp = self.path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, self.path)
        log.info("face DB saved: %d people -> %s", len(self.people), self.path)

    # ---- content ----
    def add(self, name: str, embedding) -> None:
        v = np.asarray(embedding, dtype=np.float32).ravel()
        if v.size != EMBEDDING_DIM:
            raise ValueError(f"embedding must be {EMBEDDING_DIM}-D, got {v.size}")
        self.people.setdefault(name, []).append(v)

    def remove(self, name: str) -> bool:
        return self.people.pop(name, None) is not None

    def identify(self, embedding, threshold: float = DEFAULT_THRESHOLD) -> Identification:
        return best_match(embedding, self.people, threshold)

    @property
    def names(self) -> list[str]:
        return sorted(self.people)

    def __len__(self) -> int:
        return len(self.people)


# --------------------------------------------------------------------------------------
# the only cv2-touching part
# --------------------------------------------------------------------------------------

class FaceIdentifier:
    """YuNet detection + SFace embedding + DB lookup.

    cv2 is imported lazily in __init__, consistent with the rest of the package, so
    `import kogane_base` still works without the vision extra installed.
    """

    def __init__(self, detect_model: str, recog_model: str, db_path: str,
                 threshold: float = DEFAULT_THRESHOLD,
                 score_threshold: float = 0.8,
                 nms_threshold: float = 0.3,
                 top_k: int = 500,
                 auto_download: bool = True) -> None:
        import cv2  # local import; only needed when FaceID is used

        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            raise RuntimeError(
                f"opencv {cv2.__version__} does not expose FaceDetectorYN/FaceRecognizerSF. "
                f"They live in opencv's objdetect module; install opencv-python (not the "
                f"headless-lite build) or disable FaceID with KGN_FACEID=0.")

        self._cv2 = cv2
        det_path = ensure_model(detect_model, auto_download)
        rec_path = ensure_model(recog_model, auto_download)

        self.detector = cv2.FaceDetectorYN.create(
            det_path, "", (320, 320), score_threshold, nms_threshold, top_k)
        self.recognizer = cv2.FaceRecognizerSF.create(rec_path, "")
        self.threshold = threshold
        self.db = FaceDB(db_path).load()
        self._input_size: tuple[int, int] | None = None

    # ---- primitives ----
    def detect_raw(self, image):
        """Return YuNet's raw (N, 15) face array, or None when there are no faces."""
        h, w = image.shape[:2]
        if self._input_size != (w, h):
            self.detector.setInputSize((w, h))
            self._input_size = (w, h)
        _rc, faces = self.detector.detect(image)
        return faces

    def embed(self, image, face_row) -> np.ndarray:
        """Aligned-crop then embed one face row into a 128-D vector."""
        crop = self.recognizer.alignCrop(image, face_row)
        feat = self.recognizer.feature(crop)
        return np.asarray(feat, dtype=np.float32).ravel()

    # ---- frame-level API ----
    def identify_frame(self, image) -> list[FaceObservation]:
        """Detect every face in a frame and look each one up in the DB."""
        faces = self.detect_raw(image)
        out: list[FaceObservation] = []
        if faces is None:
            return out
        for row in faces:
            x, y, bw, bh = (float(v) for v in row[:4])
            score = float(row[14]) if len(row) > 14 else 1.0
            try:
                emb = self.embed(image, row)
            except Exception as e:                    # pragma: no cover - cv2 edge cases
                log.debug("embedding failed for face at (%.0f, %.0f): %s", x, y, e)
                continue
            out.append(FaceObservation(
                x, y, x + bw, y + bh, score,
                self.db.identify(emb, self.threshold), emb))
        return out

    def enroll_frame(self, image, name: str, save: bool = True) -> FaceObservation | None:
        """Enroll the largest face in the frame under `name`.

        Largest, not first: during enrollment the subject is the one standing close to
        the camera. Returns the observation used, or None if no face was found.
        """
        faces = self.detect_raw(image)
        if faces is None or len(faces) == 0:
            return None
        rows = sorted(faces, key=lambda r: float(r[2]) * float(r[3]), reverse=True)
        row = rows[0]
        x, y, bw, bh = (float(v) for v in row[:4])
        emb = self.embed(image, row)
        self.db.add(name, emb)
        if save:
            self.db.save()
        n = len(self.db.people.get(name, []))
        log.info("enrolled %s (now %d embedding%s)", name, n, "" if n == 1 else "s")
        return FaceObservation(x, y, x + bw, y + bh,
                               float(row[14]) if len(row) > 14 else 1.0,
                               Identification(name, 1.0), emb)


def try_build_identifier(cfg, auto_download: bool = True) -> FaceIdentifier | None:
    """Build a FaceIdentifier from CONFIG, returning None (with a clear log) on failure.

    Callers that must never crash — the base station, notably — use this instead of the
    constructor so a missing model degrades FaceID to off rather than killing the run.
    """
    try:
        return FaceIdentifier(
            cfg.face_detect_model, cfg.face_recog_model, cfg.face_db_path,
            threshold=cfg.face_match_threshold,
            score_threshold=cfg.face_score_threshold,
            auto_download=auto_download,
        )
    except ModelMissingError as e:
        log.error("FaceID disabled — model missing:\n%s", e)
    except Exception as e:
        log.error("FaceID disabled — could not initialise: %s", e)
    return None
