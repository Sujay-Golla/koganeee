"""Building 320x240 RGB565 frames for the drone panel.

Two jobs live here, both pure (no sockets, no protocol):

1. Turning an arbitrary image file into something the ILI9341 can show — load, letterbox
   to exactly 320x240 so aspect ratio survives, convert to RGB565.
2. Composing a readout frame with PIL: the tracked person's name, distance, link quality
   and a small top-down plot of where they are relative to the drone.

Pillow is imported lazily. Text-mode screen output (`fmt=2`) needs no image library at all,
so the base station must still start on a machine with no Pillow installed; only the image
and panel paths require it. Pillow is in the `[vision]` and `[screen]` extras.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from ..protocol import SCREEN_H, SCREEN_W, rgb565_bytes

log = logging.getLogger("kogane.screen.frames")

PANEL_SIZE = (SCREEN_W, SCREEN_H)  # (320, 240)

# Same palette the drone's own status screen uses, so a composed frame does not look like
# it came from a different device.
C_BG = (8, 10, 14)
C_WHITE = (235, 235, 235)
C_GREY = (128, 128, 128)
C_AMBER = (255, 176, 0)
C_CYAN = (0, 200, 220)
C_GREEN = (0, 210, 90)
C_RED = (230, 60, 50)


class PillowMissing(RuntimeError):
    """Raised instead of ImportError so the CLI can print something actionable."""


def require_pil():
    """Return the Pillow modules this file needs, or raise with an install hint."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise PillowMissing(
            "this needs Pillow: pip install pillow  (or pip install -e .[screen])"
        ) from e
    return Image, ImageDraw, ImageFont


def _font(size: int):
    """A TrueType-ish default font at `size`, falling back to the bitmap font.

    `ImageFont.load_default(size=...)` uses Pillow's bundled Aileron and needs FreeType;
    on a build without it the size argument is unavailable and everything comes out at
    11 px. Legible either way, just less pretty.
    """
    _, _, ImageFont = require_pil()
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, AttributeError):  # pragma: no cover - very old/odd Pillow
        return ImageFont.load_default()


# ---- image path -----------------------------------------------------------------------
def load_image(path):
    """Load any Pillow-readable file as RGB. Flattens alpha onto the panel background."""
    Image, _, _ = require_pil()
    img = Image.open(path)
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, C_BG)
        flat.paste(img, mask=img.split()[-1])
        return flat
    return img.convert("RGB")


def letterbox(img, size: tuple[int, int] = PANEL_SIZE, bg: tuple[int, int, int] = C_BG):
    """Fit `img` inside `size` preserving aspect ratio, centred on `bg`.

    Letterboxing rather than cropping: on a 320x240 panel showing a face or a photo, black
    bars are a better failure than a cut-off head.
    """
    Image, _, _ = require_pil()
    tw, th = size
    if img.size == (tw, th):
        return img.convert("RGB")
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        raise ValueError(f"image has a zero dimension: {img.size}")
    scale = min(tw / iw, th / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = img.convert("RGB").resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), bg)
    canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def image_to_rgb565(img) -> bytes:
    """A 320x240 RGB Pillow image -> 153600 bytes of little-endian RGB565, row-major."""
    import numpy as np

    if img.size != PANEL_SIZE:
        raise ValueError(f"expected a {PANEL_SIZE[0]}x{PANEL_SIZE[1]} frame; "
                         f"got {img.size[0]}x{img.size[1]} — letterbox() it first")
    return rgb565_bytes(np.asarray(img.convert("RGB"), dtype=np.uint8))


def file_to_rgb565(path) -> bytes:
    """load -> letterbox -> RGB565. The whole image path in one call."""
    return image_to_rgb565(letterbox(load_image(path)))


# ---- readout --------------------------------------------------------------------------
@dataclass
class ReadoutState:
    """Everything the live panel shows. A plain snapshot, so it is trivial to fake.

    `None` means "not known", which is distinct from zero throughout — the same position
    `drone_state.flags` takes in PROTOCOL.md §1.
    """

    target_xy: tuple[float, float] | None = None
    fresh: bool = False
    identity: str | None = None
    link_q: int | None = None
    batt_mv: int | None = None
    drone_xy: tuple[float, float] | None = None
    room: tuple[float, float] = (4.0, 5.0)
    mode: str = ""
    note: str = ""
    trail: list[tuple[float, float]] = field(default_factory=list)

    @property
    def range_m(self) -> float | None:
        """Drone-to-target distance, if both are known."""
        if self.target_xy is None or self.drone_xy is None:
            return None
        return math.hypot(self.target_xy[0] - self.drone_xy[0],
                          self.target_xy[1] - self.drone_xy[1])


def readout_lines(state: ReadoutState) -> list[str]:
    """The readout as text rows for `fmt=2`. Pure, and each line fits 53 chars.

    This is the default live output: six small datagrams a second instead of the 120 a
    full RGB565 repaint costs, which matters on a link that is also carrying setpoints.
    """
    lines = ["KOGANE  TRACKING"]

    who = state.identity or ("tracking" if state.fresh else "no target")
    lines.append(f"WHO  {who[:48]}")

    if state.target_xy is None:
        lines.append("POS  --.-- , --.--  m")
    else:
        lines.append(f"POS  {state.target_xy[0]:5.2f} , {state.target_xy[1]:5.2f}  m")

    rng = state.range_m
    lines.append("RNG  --.-- m" if rng is None else f"RNG  {rng:5.2f} m")

    lines.append(f"TGT  {'FRESH' if state.fresh else 'STALE'}"
                 + (f"   MODE {state.mode}" if state.mode else ""))

    link = "--" if state.link_q is None else f"{state.link_q:3d}"
    batt = "" if state.batt_mv is None else f"   BATT {state.batt_mv / 1000.0:.2f} V"
    lines.append(f"LINK {link}{batt}")

    if state.note:
        lines.append(state.note)
    return lines


def compose_readout(state: ReadoutState, size: tuple[int, int] = PANEL_SIZE):
    """The same readout as a composed PIL frame, with a top-down position plot.

    Layout: title bar, a left-hand text block, and a right-hand plan view of the room with
    the drone as a circle and the target as a cross plus its recent trail.
    """
    Image, ImageDraw, _ = require_pil()
    w, h = size
    img = Image.new("RGB", (w, h), C_BG)
    d = ImageDraw.Draw(img)

    f_title = _font(22)
    f_body = _font(15)
    f_small = _font(12)

    # title bar
    d.rectangle([0, 0, w - 1, 30], fill=(20, 24, 32))
    d.text((8, 4), "KOGANE", font=f_title, fill=C_AMBER)
    status, colour = ("FRESH", C_GREEN) if state.fresh else ("STALE", C_RED)
    d.text((w - 62, 8), status, font=f_body, fill=colour)
    d.line([0, 31, w - 1, 31], fill=C_GREY)

    # text block
    x, y = 8, 42
    rows: list[tuple[str, str, tuple[int, int, int]]] = [
        ("WHO", state.identity or ("-- tracking --" if state.fresh else "-- none --"),
         C_WHITE if state.identity else C_GREY),
        ("POS", "--" if state.target_xy is None
         else f"{state.target_xy[0]:.2f}, {state.target_xy[1]:.2f} m", C_CYAN),
        ("RNG", "--" if state.range_m is None else f"{state.range_m:.2f} m", C_CYAN),
        ("LINK", "--" if state.link_q is None else f"{state.link_q} %",
         C_GREEN if (state.link_q or 0) >= 40 else C_AMBER),
    ]
    if state.batt_mv is not None:
        rows.append(("BATT", f"{state.batt_mv / 1000.0:.2f} V", C_WHITE))
    if state.mode:
        rows.append(("MODE", state.mode, C_AMBER))
    for label, value, colour in rows:
        d.text((x, y), label, font=f_small, fill=C_GREY)
        d.text((x + 44, y - 2), value, font=f_body, fill=colour)
        y += 26

    if state.note:
        d.text((x, h - 18), state.note[:40], font=f_small, fill=C_GREY)

    _draw_plan(d, state, box=(w - 122, 44, w - 10, 228))
    return img


def _draw_plan(d, state: ReadoutState, box: tuple[int, int, int, int]) -> None:
    """Plan view of the room inside `box` = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], outline=C_GREY)
    room_w, room_l = state.room
    if room_w <= 0 or room_l <= 0:
        return

    def to_px(p: tuple[float, float]) -> tuple[int, int]:
        # Room +y runs away from the viewer, so it maps to decreasing screen y.
        fx = min(max(p[0] / room_w, 0.0), 1.0)
        fy = min(max(p[1] / room_l, 0.0), 1.0)
        return (int(x0 + 1 + fx * (x1 - x0 - 2)),
                int(y1 - 1 - fy * (y1 - y0 - 2)))

    # 1 m grid
    for i in range(1, int(room_w)):
        gx = to_px((i, 0))[0]
        d.line([gx, y0 + 1, gx, y1 - 1], fill=(30, 34, 42))
    for j in range(1, int(room_l)):
        gy = to_px((0, j))[1]
        d.line([x0 + 1, gy, x1 - 1, gy], fill=(30, 34, 42))

    for pt in state.trail[-24:]:
        px, py = to_px(pt)
        d.point((px, py), fill=(60, 90, 100))

    if state.drone_xy is not None:
        px, py = to_px(state.drone_xy)
        d.ellipse([px - 4, py - 4, px + 4, py + 4], outline=C_AMBER)
        d.point((px, py), fill=C_AMBER)

    if state.target_xy is not None:
        px, py = to_px(state.target_xy)
        colour = C_GREEN if state.fresh else C_RED
        d.line([px - 5, py, px + 5, py], fill=colour)
        d.line([px, py - 5, px, py + 5], fill=colour)

    if state.drone_xy is not None and state.target_xy is not None:
        d.line([to_px(state.drone_xy), to_px(state.target_xy)], fill=(70, 80, 90))


def compose_demo(title: str = "KOGANE", subtitle: str = "screen link up",
                 size: tuple[int, int] = PANEL_SIZE):
    """A self-contained frame that proves the RGB565 path without any live state.

    Colour bars along the bottom make a byte-order or bit-packing mistake obvious at a
    glance: get red and blue swapped and the bars come out in the wrong order.
    """
    Image, ImageDraw, _ = require_pil()
    w, h = size
    img = Image.new("RGB", (w, h), C_BG)
    d = ImageDraw.Draw(img)

    d.text((10, 14), title, font=_font(40), fill=C_AMBER)
    d.text((12, 66), subtitle, font=_font(16), fill=C_WHITE)
    d.text((12, 90), f"{w}x{h} RGB565  320x32 band", font=_font(12), fill=C_GREY)

    # concentric rings: any torn or missing strip shows up as a break in a circle
    cx, cy = w - 74, 96
    for i, r in enumerate((44, 34, 24, 14)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  outline=(C_CYAN, C_AMBER, C_GREEN, C_WHITE)[i])

    bars = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
            (0, 255, 255), (255, 0, 255), (255, 255, 255), (0, 0, 0)]
    bw = w / len(bars)
    for i, colour in enumerate(bars):
        d.rectangle([int(i * bw), h - 60, int((i + 1) * bw) - 1, h - 20], fill=colour)
    d.text((10, h - 16), "R G B Y C M W K", font=_font(12), fill=C_GREY)
    return img
