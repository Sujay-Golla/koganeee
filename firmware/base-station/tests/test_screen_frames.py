"""Tests for kogane_base.screen.frames and the three CLI front ends.

The frame tests need Pillow and skip without it, because text-mode screen output does not
require it and the base station must still run on a host that has no image library.
The CLI tests use `--dry-run`, so no socket is opened and no drone is contacted.
"""
from __future__ import annotations

import numpy as np
import pytest

from kogane_base import protocol as p
from kogane_base.screen import frames as fr

PIL = pytest.importorskip("PIL", reason="the image paths need Pillow ([screen] extra)")
from PIL import Image  # noqa: E402


# ---- letterbox -----------------------------------------------------------
def test_letterbox_hits_the_panel_size_exactly():
    for size in [(640, 480), (1920, 1080), (100, 900), (320, 240), (7, 3)]:
        out = fr.letterbox(Image.new("RGB", size, (255, 0, 0)))
        assert out.size == fr.PANEL_SIZE


def test_letterbox_preserves_aspect_ratio_and_pads_the_rest():
    """A 640x240 source is twice as wide as the panel, so it fills the width and is
    centred vertically with background bars above and below."""
    out = fr.letterbox(Image.new("RGB", (640, 240), (255, 0, 0)))
    px = np.asarray(out)
    assert tuple(px[120, 160]) == (255, 0, 0)       # centre is image
    assert tuple(px[0, 160]) == fr.C_BG             # top is padding
    assert tuple(px[239, 160]) == fr.C_BG           # bottom is padding


def test_letterbox_pads_the_sides_for_a_tall_source():
    out = fr.letterbox(Image.new("RGB", (240, 640), (0, 255, 0)))
    px = np.asarray(out)
    assert tuple(px[120, 160]) == (0, 255, 0)
    assert tuple(px[120, 0]) == fr.C_BG
    assert tuple(px[120, 319]) == fr.C_BG


def test_letterbox_leaves_an_already_correct_frame_alone():
    src = Image.new("RGB", fr.PANEL_SIZE, (1, 2, 3))
    assert fr.letterbox(src).tobytes() == src.tobytes()


def test_letterbox_rejects_a_zero_dimension_image():
    with pytest.raises(ValueError, match="zero dimension"):
        fr.letterbox(Image.new("RGB", (0, 10)))


# ---- conversion ----------------------------------------------------------
def test_image_to_rgb565_length_is_two_bytes_per_pixel():
    data = fr.image_to_rgb565(Image.new("RGB", fr.PANEL_SIZE))
    assert len(data) == 320 * 240 * 2 == 153600


def test_image_to_rgb565_matches_the_protocol_packer():
    img = Image.new("RGB", fr.PANEL_SIZE, (255, 0, 0))
    assert fr.image_to_rgb565(img)[:2] == b"\x00\xf8"       # 0xF800 little-endian
    assert fr.image_to_rgb565(img) == p.rgb565_bytes(np.asarray(img))


def test_image_to_rgb565_refuses_a_wrong_sized_frame():
    with pytest.raises(ValueError, match="letterbox"):
        fr.image_to_rgb565(Image.new("RGB", (100, 100)))


def test_file_to_rgb565_round_trip(tmp_path):
    path = tmp_path / "in.png"
    Image.new("RGB", (640, 480), (0, 0, 255)).save(path)
    data = fr.file_to_rgb565(path)
    assert len(data) == 153600
    back = p.rgb565_to_rgb(data, 320, 240)
    assert tuple(back[120, 160]) == (0, 0, 248)      # blue, minus the dropped low bits


def test_load_image_flattens_alpha_onto_the_panel_background(tmp_path):
    path = tmp_path / "a.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 0)).save(path)
    img = fr.load_image(path)
    assert img.mode == "RGB"
    assert tuple(np.asarray(img)[8, 8]) == fr.C_BG


def test_load_image_converts_greyscale(tmp_path):
    path = tmp_path / "g.png"
    Image.new("L", (16, 16), 128).save(path)
    assert fr.load_image(path).mode == "RGB"


# ---- composed frames ----------------------------------------------------
def test_compose_demo_is_a_sendable_panel_frame():
    img = fr.compose_demo()
    assert img.size == fr.PANEL_SIZE
    data = fr.image_to_rgb565(img)
    from kogane_base.screen.sender import image_payloads
    assert len(image_payloads(data, strip_rows=2)) == 120


def test_compose_demo_colour_bars_are_in_the_documented_order():
    """Red first, black last. Swap red and blue in the packer and this fails."""
    px = np.asarray(fr.compose_demo())
    y = 240 - 40
    assert tuple(px[y, 10]) == (255, 0, 0)
    assert tuple(px[y, 50]) == (0, 255, 0)
    assert tuple(px[y, 90]) == (0, 0, 255)
    assert tuple(px[y, 310]) == (0, 0, 0)


def test_compose_readout_renders_with_everything_known():
    state = fr.ReadoutState(target_xy=(1.2, 3.4), fresh=True, identity="sujay",
                            link_q=91, batt_mv=11400, drone_xy=(2.0, 2.5),
                            room=(4.0, 5.0), mode="FOLLOW", note="gesture: come here",
                            trail=[(1.0 + i * 0.05, 3.0) for i in range(30)])
    img = fr.compose_readout(state)
    assert img.size == fr.PANEL_SIZE
    assert len(fr.image_to_rgb565(img)) == 153600


def test_compose_readout_renders_with_nothing_known():
    img = fr.compose_readout(fr.ReadoutState())
    assert img.size == fr.PANEL_SIZE


def test_compose_readout_survives_a_degenerate_room():
    img = fr.compose_readout(fr.ReadoutState(room=(0.0, 0.0), target_xy=(1.0, 1.0)))
    assert img.size == fr.PANEL_SIZE


def test_compose_readout_clamps_a_target_outside_the_room():
    img = fr.compose_readout(fr.ReadoutState(target_xy=(-99.0, 999.0), fresh=True,
                                             drone_xy=(2.0, 2.0), room=(4.0, 5.0)))
    assert img.size == fr.PANEL_SIZE


# ---- kogane-screen -------------------------------------------------------
def test_parse_colour_accepts_names_hex_and_triples():
    from kogane_base.tools.screen_cli import parse_colour

    assert parse_colour("red") == p.RGB565_RED
    assert parse_colour("AMBER") == p.RGB565_AMBER
    assert parse_colour("0xF800") == p.RGB565_RED
    assert parse_colour("#ff0000") == p.RGB565_RED
    assert parse_colour("255,0,0") == p.RGB565_RED
    assert parse_colour("0") == 0


def test_parse_colour_rejects_nonsense():
    import argparse

    from kogane_base.tools.screen_cli import parse_colour

    for bad in ["chartreuse", "#ff00", "1,2", "0x1FFFF"]:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_colour(bad)


def test_screen_cli_pairs_text_with_rows():
    from kogane_base.tools.screen_cli import _pair_text_rows

    assert _pair_text_rows(["a", "b", "c"], []) == [(0, "a"), (1, "b"), (2, "c")]
    assert _pair_text_rows(["a", "b"], [5]) == [(5, "a"), (6, "b")]
    assert _pair_text_rows(["a", "b"], [0, 4]) == [(0, "a"), (4, "b")]


def test_screen_cli_dry_run_text(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--text", "hello there", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "TEXT row 0" in out
    assert "1 SCREEN_FRAME chunk(s) sent" in out


def test_screen_cli_dry_run_status(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--status", "--dry-run"]) == 0
    assert "panel released" in capsys.readouterr().out


def test_screen_cli_dry_run_demo_sends_120_strips(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--demo", "--dry-run", "--strip-delay-ms", "0"]) == 0
    assert "120 strip(s)" in capsys.readouterr().out


def test_screen_cli_dry_run_image(tmp_path, capsys):
    from kogane_base.tools.screen_cli import main

    path = tmp_path / "pic.png"
    Image.new("RGB", (800, 600), (0, 128, 255)).save(path)
    assert main(["--image", str(path), "--dry-run", "--strip-delay-ms", "0"]) == 0
    out = capsys.readouterr().out
    assert "800x600 -> letterboxed to 320x240" in out
    assert "120 strip(s)" in out


def test_screen_cli_with_no_action_explains_itself(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--dry-run"]) == 2
    assert "nothing to send" in capsys.readouterr().err


def test_screen_cli_rejects_a_row_past_the_grid(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--text", "x", "--row", "10", "--dry-run"]) == 1
    assert "outside 0..9" in capsys.readouterr().err


def test_screen_cli_reports_a_missing_image_file(capsys):
    from kogane_base.tools.screen_cli import main

    assert main(["--image", "no/such/file.png", "--dry-run"]) == 1
    assert "FAILED" in capsys.readouterr().err


# ---- kogane-audio --------------------------------------------------------
def test_audio_cli_dry_run_selftest(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--selftest", "--dry-run"]) == 0
    assert "CTRL SELFTEST" in capsys.readouterr().out


def test_audio_cli_dry_run_tone(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--tone", "--seconds", "0.1", "--no-pace", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "TONE 660 Hz" in out
    assert "5 chunk(s)" in out


def test_audio_cli_dry_run_wav(tmp_path, capsys):
    from kogane_base.audio.wav import tone, write_wav
    from kogane_base.tools.audio_cli import main

    path = write_wav(tmp_path / "t.wav", tone(440, 0.1))
    assert main(["--wav", str(path), "--no-pace", "--dry-run"]) == 0
    assert "16000 Hz, 1 ch, 16-bit" in capsys.readouterr().out


def test_audio_cli_dry_run_mic_toggles(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--mic-on", "--mic-off", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "CTRL MIC_ON" in out and "CTRL MIC_OFF" in out


def test_audio_cli_rejects_an_oversized_chunk(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--tone", "--chunk-ms", "60", "--dry-run"]) == 2
    assert "drops anything over 1440" in capsys.readouterr().err


def test_audio_cli_with_no_action_explains_itself(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--dry-run"]) == 2
    assert "nothing to do" in capsys.readouterr().err


def test_audio_cli_record_needs_a_real_socket(capsys):
    from kogane_base.tools.audio_cli import main

    assert main(["--record", "out.wav", "--dry-run"]) == 2
    assert "nothing to listen to" in capsys.readouterr().err


# ---- kogane-say ----------------------------------------------------------
def test_say_wraps_text_for_the_panel():
    from kogane_base.tools.say_cli import wrap_for_panel

    lines = wrap_for_panel("hello there I am kogane and I follow you around the room")
    assert len(lines) <= 4
    assert all(len(ln) <= 26 for ln in lines)
    assert lines[0].startswith("hello")


def test_say_wrap_truncates_rather_than_overflowing():
    from kogane_base.tools.say_cli import wrap_for_panel

    lines = wrap_for_panel(" ".join(["word"] * 200))
    assert len(lines) == 4


def test_say_wrap_handles_a_single_overlong_word():
    from kogane_base.tools.say_cli import wrap_for_panel

    assert wrap_for_panel("x" * 100) == ["x" * 26]


def test_say_with_no_text_explains_itself(capsys):
    from kogane_base.tools.say_cli import main

    assert main([]) == 2
    assert "nothing to say" in capsys.readouterr().err
