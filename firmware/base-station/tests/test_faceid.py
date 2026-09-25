"""FaceID matching logic on synthetic 128-D embeddings. No cv2, no ONNX, no camera."""
from __future__ import annotations

import json

import numpy as np
import pytest

from kogane_base.vision.faceid import (DEFAULT_THRESHOLD, EMBEDDING_DIM, FaceDB,
                                       FaceObservation, Identification,
                                       assign_face_to_track, best_match,
                                       cosine_similarity, resolve_locked_id)
from kogane_base.vision.models import (MODEL_SOURCES, ModelMissingError, ensure_model,
                                       urls_for)


def unit(seed: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    """A deterministic random embedding."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def nudged(v: np.ndarray, noise: float, seed: int = 99) -> np.ndarray:
    """Same identity, different lighting/angle: a small perturbation."""
    rng = np.random.default_rng(seed)
    out = v + rng.normal(scale=noise, size=v.shape).astype(np.float32)
    return out / np.linalg.norm(out)


# ---- cosine similarity ----

def test_identical_vectors_similarity_one():
    v = unit(1)
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_opposite_vectors_similarity_minus_one():
    v = unit(2)
    assert cosine_similarity(v, -v) == pytest.approx(-1.0, abs=1e-6)


def test_orthogonal_vectors_similarity_zero():
    a = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    b = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    a[0], b[1] = 1.0, 1.0
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_similarity_is_scale_invariant():
    """SFace embeddings are not unit-norm, so magnitude must not matter."""
    v = unit(3)
    assert cosine_similarity(v * 17.0, v * 0.03) == pytest.approx(1.0, abs=1e-6)


def test_similarity_is_symmetric():
    a, b = unit(4), unit(5)
    assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))


def test_zero_vector_gives_zero_not_nan():
    assert cosine_similarity(np.zeros(EMBEDDING_DIM), unit(6)) == 0.0
    assert cosine_similarity(np.zeros(EMBEDDING_DIM), np.zeros(EMBEDDING_DIM)) == 0.0


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        cosine_similarity(np.zeros(128), np.zeros(64))


def test_accepts_the_1x128_shape_opencv_returns():
    """cv2's feature() returns (1, 128); ravel must make that comparable to (128,)."""
    v = unit(7)
    assert cosine_similarity(v.reshape(1, -1), v) == pytest.approx(1.0, abs=1e-6)


def test_random_128d_vectors_are_far_below_threshold():
    """Two strangers should not match. Random high-dim vectors are near-orthogonal."""
    for s in range(10):
        sim = cosine_similarity(unit(100 + s), unit(200 + s))
        assert abs(sim) < DEFAULT_THRESHOLD


# ---- best_match / threshold behaviour ----

def test_empty_db_returns_unknown():
    ident = best_match(unit(1), {})
    assert not ident.known
    assert ident.name is None
    assert ident.score == 0.0


def test_db_with_only_empty_lists_returns_unknown():
    assert not best_match(unit(1), {"ghost": []}).known


def test_exact_enrolled_face_is_recognised():
    a = unit(11)
    ident = best_match(a, {"alice": [a], "bob": [unit(12)]})
    assert ident.name == "alice"
    assert ident.score == pytest.approx(1.0, abs=1e-6)


def test_same_person_slightly_different_is_recognised():
    a = unit(13)
    ident = best_match(nudged(a, 0.2), {"alice": [a], "bob": [unit(14)]})
    assert ident.name == "alice"
    assert ident.score > DEFAULT_THRESHOLD


def test_stranger_is_rejected_as_unknown():
    ident = best_match(unit(15), {"alice": [unit(16)], "bob": [unit(17)]})
    assert not ident.known
    assert ident.name is None
    assert ident.score < DEFAULT_THRESHOLD    # score still reported for debugging


def test_threshold_is_the_only_thing_separating_known_from_unknown():
    a = unit(18)
    probe = nudged(a, 1.2, seed=7)            # degraded but still correlated
    sim = cosine_similarity(probe, a)
    assert 0.0 < sim < 1.0
    assert best_match(probe, {"alice": [a]}, threshold=sim - 0.01).name == "alice"
    assert best_match(probe, {"alice": [a]}, threshold=sim + 0.01).name is None


def test_threshold_boundary_accepts_scores_at_or_above_it():
    """`score < threshold` rejects, so a score exactly at the threshold is accepted."""
    a = unit(19)
    score = cosine_similarity(a, a)          # ~1.0 but not bit-exactly 1.0
    assert best_match(a, {"alice": [a]}, threshold=score).name == "alice"
    assert best_match(a, {"alice": [a]}, threshold=score + 1e-9).name is None


def test_threshold_of_one_rejects_because_float_cosine_never_quite_reaches_it():
    """Documents a real trap: don't configure KGN_FACE_THRESHOLD=1.0 expecting exact matches."""
    a = unit(19)
    assert cosine_similarity(a, a) < 1.0 or cosine_similarity(a, a) == 1.0
    assert best_match(a, {"alice": [a]}, threshold=1.0000001).name is None


def test_multiple_embeddings_per_person_take_the_best():
    a = unit(20)
    decoys = [unit(21), unit(22)]
    # alice's good embedding is buried behind two poor ones
    ident = best_match(a, {"alice": decoys + [a]})
    assert ident.name == "alice"
    assert ident.score == pytest.approx(1.0, abs=1e-6)


def test_closest_person_wins_among_several():
    a, b, c = unit(23), unit(24), unit(25)
    ident = best_match(nudged(b, 0.15), {"alice": [a], "bob": [b], "carol": [c]})
    assert ident.name == "bob"


def test_runner_up_and_margin_reported():
    a, b = unit(26), unit(27)
    ident = best_match(a, {"alice": [a], "bob": [b]})
    assert ident.runner_up == pytest.approx(cosine_similarity(a, b))
    assert ident.margin > 0.5      # confident: a matches itself far better than b


# ---- FaceDB persistence ----

def test_db_load_of_missing_file_is_empty_not_an_error(tmp_path):
    db = FaceDB(str(tmp_path / "nothing.json")).load()
    assert len(db) == 0
    assert db.names == []


def test_db_save_load_round_trip(tmp_path):
    path = tmp_path / "sub" / "faces.json"
    db = FaceDB(str(path))
    a, b = unit(31), unit(32)
    db.add("alice", a)
    db.add("alice", nudged(a, 0.1))
    db.add("bob", b)
    db.save()
    assert path.exists()

    back = FaceDB(str(path)).load()
    assert back.names == ["alice", "bob"]
    assert len(back.people["alice"]) == 2
    assert back.identify(a).name == "alice"
    assert back.identify(b).name == "bob"
    np.testing.assert_allclose(back.people["bob"][0], b, atol=1e-6)


def test_db_file_is_readable_json_with_metadata(tmp_path):
    path = tmp_path / "faces.json"
    db = FaceDB(str(path))
    db.add("alice", unit(33))
    db.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["type"] == "kogane.face_db"
    assert raw["dim"] == EMBEDDING_DIM
    assert "alice" in raw["people"]
    assert len(raw["people"]["alice"][0]) == EMBEDDING_DIM


def test_db_rejects_wrong_width_embedding(tmp_path):
    db = FaceDB(str(tmp_path / "f.json"))
    with pytest.raises(ValueError, match="128-D"):
        db.add("alice", np.zeros(64))


def test_db_skips_corrupt_entries_on_load(tmp_path):
    path = tmp_path / "faces.json"
    path.write_text(json.dumps({
        "type": "kogane.face_db", "version": 1, "dim": 128,
        "people": {"good": [unit(34).tolist()], "bad": [[1.0, 2.0, 3.0]]},
    }), encoding="utf-8")
    db = FaceDB(str(path)).load()
    assert db.names == ["good"]


def test_db_unreadable_file_degrades_to_empty(tmp_path):
    path = tmp_path / "faces.json"
    path.write_text("{{{ not json", encoding="utf-8")
    db = FaceDB(str(path)).load()
    assert len(db) == 0


def test_db_remove(tmp_path):
    db = FaceDB(str(tmp_path / "f.json"))
    db.add("alice", unit(35))
    assert db.remove("alice") is True
    assert db.remove("alice") is False
    assert db.names == []


# ---- face box -> person track assignment ----

class FakeTrack:
    def __init__(self, x1, y1, x2, y2, track_id):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.track_id = track_id


def test_face_assigned_to_containing_person_box():
    near = FakeTrack(100, 100, 200, 400, 1)
    other = FakeTrack(400, 100, 500, 400, 2)
    face = (130.0, 110.0, 170.0, 150.0)     # inside `near`'s head region
    assert assign_face_to_track(face, [other, near]) is near


def test_face_outside_every_box_assigned_to_nobody():
    t = FakeTrack(100, 100, 200, 400, 1)
    assert assign_face_to_track((600.0, 600.0, 640.0, 640.0), [t]) is None


def test_overlapping_people_smallest_containing_box_wins():
    """A big foreground box can swallow a background person's face; prefer the tight one."""
    foreground = FakeTrack(50, 50, 600, 470, 1)     # huge, close to camera
    background = FakeTrack(300, 120, 360, 300, 2)   # small, further away
    face = (320.0, 130.0, 345.0, 160.0)             # this is the background person's face
    assert assign_face_to_track(face, [foreground, background]) is background


def test_face_on_box_border_counts_as_inside():
    t = FakeTrack(100, 100, 200, 400, 1)
    # face centre exactly on the left edge
    assert assign_face_to_track((80.0, 150.0, 120.0, 190.0), [t]) is t


def test_assign_with_no_tracks():
    assert assign_face_to_track((0.0, 0.0, 10.0, 10.0), []) is None


# ---- locked_id resolution ----

def obs(x1, y1, x2, y2, name, score):
    return FaceObservation(x1, y1, x2, y2, 0.99, Identification(name, score))


def test_recognised_face_sets_locked_id():
    t = FakeTrack(100, 100, 200, 400, 7)
    assert resolve_locked_id([obs(130, 110, 170, 150, "alice", 0.8)], [t]) == 7


def test_unknown_faces_do_not_lock():
    t = FakeTrack(100, 100, 200, 400, 7)
    assert resolve_locked_id([obs(130, 110, 170, 150, None, 0.2)], [t]) is None


def test_no_faces_no_lock():
    assert resolve_locked_id([], [FakeTrack(0, 0, 10, 10, 1)]) is None


def test_highest_scoring_recognised_face_wins():
    t1 = FakeTrack(100, 100, 200, 400, 1)
    t2 = FakeTrack(300, 100, 400, 400, 2)
    faces = [obs(130, 110, 170, 150, "alice", 0.55),
             obs(330, 110, 370, 150, "bob", 0.91)]
    assert resolve_locked_id(faces, [t1, t2]) == 2


def test_prefer_restricts_to_named_people():
    t1 = FakeTrack(100, 100, 200, 400, 1)
    t2 = FakeTrack(300, 100, 400, 400, 2)
    faces = [obs(130, 110, 170, 150, "alice", 0.55),
             obs(330, 110, 370, 150, "bob", 0.91)]
    assert resolve_locked_id(faces, [t1, t2], prefer={"alice"}) == 1
    assert resolve_locked_id(faces, [t1, t2], prefer={"nobody"}) is None


def test_untracked_person_cannot_be_locked():
    """track_id -1 means ByteTrack has no id yet; locking onto it would be meaningless."""
    t = FakeTrack(100, 100, 200, 400, -1)
    assert resolve_locked_id([obs(130, 110, 170, 150, "alice", 0.9)], [t]) is None


def test_face_observation_label_text():
    known = obs(0, 0, 10, 10, "alice", 0.87)
    assert known.label == "alice 0.87"
    assert "unknown" in obs(0, 0, 10, 10, None, 0.12).label


# ---- model resolution ----

def test_known_models_have_two_candidate_urls():
    for name in MODEL_SOURCES:
        urls = urls_for(name)
        assert len(urls) == 2
        assert urls[0].startswith("https://media.githubusercontent.com/media/")
        assert name in urls[0]


def test_ensure_model_without_download_gives_actionable_error(tmp_path):
    missing = tmp_path / "face_detection_yunet_2023mar.onnx"
    with pytest.raises(ModelMissingError) as ei:
        ensure_model(str(missing), auto_download=False)
    msg = str(ei.value)
    assert "opencv_zoo" in msg
    assert str(missing) in msg


def test_ensure_model_rejects_unknown_filename(tmp_path):
    with pytest.raises(ModelMissingError, match="cannot be fetched automatically"):
        ensure_model(str(tmp_path / "mystery.onnx"), auto_download=True)


def test_ensure_model_accepts_an_existing_plausible_file(tmp_path):
    p = tmp_path / "face_detection_yunet_2023mar.onnx"
    p.write_bytes(b"\x08\x01" + b"\x00" * 200_000)     # big enough, not an LFS pointer
    assert ensure_model(str(p), auto_download=False) == str(p)


def test_ensure_model_refuses_a_git_lfs_pointer_file(tmp_path):
    p = tmp_path / "face_detection_yunet_2023mar.onnx"
    p.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
    with pytest.raises(ModelMissingError):
        ensure_model(str(p), auto_download=False)


def test_ensure_model_refuses_a_truncated_file(tmp_path):
    p = tmp_path / "face_recognition_sface_2021dec.onnx"
    p.write_bytes(b"\x00" * 1024)          # far below the 1 MB minimum
    with pytest.raises(ModelMissingError):
        ensure_model(str(p), auto_download=False)
