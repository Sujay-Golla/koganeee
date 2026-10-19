"""A light, architectural dashboard drawn at the requested pixel density.

Presentation only. Sensor measurements and tracking remain in their own modules.
"""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

BG = "#f6f4ef"
PAPER = "#fdfcf9"
MAP = "#eeece5"
LINE = "#d6d2c8"
INK = "#292d29"
MUTED = "#686d64"
FAINT = "#888a7e"
ACCENT = "#ad4f35"
TEAL = "#466853"  # Connection status, separate from the terracotta position marker.
GOLD = "#946923"
BLUE = "#677a83"
RED = "#a44134"


@lru_cache(maxsize=48)
def font(size, bold=False, family="sans"):
    if family == "serif":
        names = ["C:/Windows/Fonts/georgia.ttf", "DejaVuSerif.ttf"]
    elif family == "number":
        names = ["C:/Windows/Fonts/bahnschrift.ttf", "DejaVuSans.ttf"]
    else:
        names = (["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf"] if bold else
                 ["C:/Windows/Fonts/segoeui.ttf"])
        names += ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for path in names:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=192)
def scaled_font(face, scale):
    return face.font_variant(size=max(1, round(face.size*scale)))


class DensityDraw:
    """Keep the 1280x720 layout, rasterizing geometry and fonts at native density.

    Layout measurements stay in logical units. No low-resolution dashboard image
    is enlarged to manufacture the higher-resolution text or map.
    """

    def __init__(self, canvas, scale):
        self.draw = ImageDraw.Draw(canvas)
        self.scale = scale

    def coords(self, values):
        return tuple(self.coords(value) if isinstance(value, (tuple, list, np.ndarray))
                     else value*self.scale for value in values)

    def text(self, xy, value, *, font, **kwargs):
        self.draw.text(self.coords(xy), value, font=scaled_font(font, self.scale), **kwargs)

    def textlength(self, value, *, font):
        return self.draw.textlength(value, font=font)

    def line(self, xy, fill=None, width=1):
        self.draw.line(self.coords(xy), fill=fill, width=max(1, round(width*self.scale)))

    def rectangle(self, xy, fill=None, outline=None, width=1):
        self.draw.rectangle(self.coords(xy), fill=fill, outline=outline,
                            width=max(1, round(width*self.scale)))

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self.draw.ellipse(self.coords(xy), fill=fill, outline=outline,
                          width=max(1, round(width*self.scale)))

    def polygon(self, xy, fill=None):
        self.draw.polygon(self.coords(xy), fill=fill)


def text(draw, xy, value, size=16, color=INK, bold=False, anchor=None, family="sans"):
    draw.text(xy, str(value), font=font(size, bold, family), fill=color, anchor=anchor)


def fit_text(draw, xy, value, width, size=16, color=INK, bold=False):
    value = str(value)
    f = font(size, bold)
    if draw.textlength(value, font=f) > width:
        while value and draw.textlength(value+"…", font=f) > width:
            value = value[:-1]
        value += "…"
    draw.text(xy, value, font=f, fill=color)


def caps(draw, xy, value, color=MUTED, size=10, spacing=1.8):
    x, y = xy
    for char in value.upper():
        text(draw, (x, y), char, size, color, True)
        x += draw.textlength(char, font=font(size, True))+spacing


def dot(draw, x, y, color, radius=4):
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)


def radar_message(status, points):
    if status.startswith("LIVE"):
        n = len(points)
        return (f"{n} detection" + ("s" if n != 1 else ""), TEAL, "Reports are up to date")
    if status == "STALE":
        return "Paused", GOLD, "Waiting for fresh reports"
    if status.startswith("ERROR"):
        return "Check connection", GOLD, "Check USB and the radar wires"
    if status == "NOT CONNECTED":
        return "Not connected", MUTED, "Connect the radar when ready"
    if status == "PREVIEW ONLY":
        return "Example data", GOLD, "Layout preview only"
    return "Connecting", GOLD, "Waiting for the first report"


def presentation(stereo, views, now, room):
    """Do not display an old depth or position as a current reading."""
    target = stereo["target"]
    live = bool(stereo.get("valid") and target.fresh(now) and
                all(math.isfinite(v) for v in target.xy))
    depth = stereo.get("depth_m")
    depth = float(depth) if live and depth is not None and math.isfinite(depth) and depth > 0 else None
    live = live and depth is not None
    status = stereo.get("status", "")
    radar_mode = stereo.get("position_source") == "radar"
    if radar_mode and live:
        heading, helper = "Position available", "Position measured by the room radar"
    elif radar_mode and status == "MULTIPLE RADAR TARGETS":
        heading, helper = "Multiple detections", "Use one person for this demonstration"
    elif radar_mode and status == "NO RADAR TARGET":
        heading, helper = "Waiting for movement", "Move within the radar's viewing area"
    elif radar_mode and status == "RADAR ERROR":
        heading, helper = "Check radar connection", "Check USB, power and the radar wires"
    elif radar_mode:
        heading, helper = "Waiting for radar", "Position needs fresh radar reports"
    elif live:
        heading, helper = "Person tracked", "Both cameras have a depth measurement"
    elif "NO PERSON" in status:
        heading, helper = "Step into view", "Stand where both cameras can see you"
    elif "MATCH" in status:
        heading, helper = "Finding depth", "Stay in both views and pause briefly"
    elif any(v.status not in ("LIVE", "OPENING") for v in views):
        heading, helper = "Check a camera", "A camera is disconnected or unavailable"
    else:
        heading, helper = "Waiting for cameras", "Depth needs a fresh image from each camera"
    lateral, forward = "—", "—"
    if live:
        delta = target.xy[0]-room[0]/2
        lateral = "Near centre" if abs(delta) < .20 else f"{abs(delta):.1f} m {'left' if delta < 0 else 'right'}"
        forward = f"{target.xy[1]:.1f} m into room"
    return dict(live=live, depth=depth, heading=heading, helper=helper,
                lateral=lateral, forward=forward)


def point(xy, room, bounds):
    x, y = xy
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= room[0] and 0 <= y <= room[1]):
        return None
    l, t, r, b = bounds
    return l+x/room[0]*(r-l), b-y/room[1]*(b-t)


def draw_camera(canvas, draw, view, bounds, title, now):
    """Letterbox the complete source image, retaining its original field of view."""
    import cv2
    x, y, r, b = bounds
    live = view.frame_live(now)
    caps(draw, (x, y), title, size=10, spacing=1.2)
    dot(draw, r-4, y+7, TEAL if live else GOLD, 3)
    ax, ay, ar, ab = x, y+27, r, b-26
    draw.rectangle((ax, ay, ar, ab), fill="#e2dfd6")
    if view.frame is not None:
        image = view.frame.image.copy()
        if live:
            for track in view.tracks:
                cv2.rectangle(image, (int(track.x1), int(track.y1)),
                              (int(track.x2), int(track.y2)), (112, 179, 208), 2)
            for obj in getattr(view, "objects", []):
                x1, y1, x2, y2 = (int(v) for v in (obj.x1, obj.y1, obj.x2, obj.y2))
                cv2.rectangle(image, (x1, y1), (x2, y2), (168, 128, 85), 2)
                cv2.putText(image, obj.label, (x1, max(18, y1-7)), cv2.FONT_HERSHEY_SIMPLEX,
                            .55, (210, 186, 156), 2, cv2.LINE_AA)
        image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        scale = draw.scale
        pw, ph = round((ar-ax)*scale), round((ab-ay)*scale)
        ratio = min(pw/image.width, ph/image.height)
        image = image.resize((max(1, round(image.width*ratio)), max(1, round(image.height*ratio))),
                             Image.Resampling.LANCZOS)
        if not live:
            image = ImageEnhance.Color(image).enhance(0)
            image = ImageEnhance.Brightness(image).enhance(.35)
        canvas.paste(image, (round(ax*scale)+(pw-image.width)//2,
                             round(ay*scale)+(ph-image.height)//2))
    if not live:
        # An opaque caption remains legible over a stale source frame.
        label = "Waiting for video"
        cx, cy = (ax+ar)/2, (ay+ab)/2
        tw = draw.textlength(label, font=font(12))
        draw.rectangle((cx-tw/2-9, cy-13, cx+tw/2+9, cy+13), fill=PAPER)
        text(draw, (cx, cy), label, 12, MUTED, anchor="mm")
    camera_caption = getattr(view, "object_status", "") if live else "No current image"
    fit_text(draw, (x, b-17), camera_caption or "Live image", r-x-54, 10, MUTED)
    text(draw, (r, b-17), f"CAM {view.index:02}", 10, FAINT, anchor="ra")


def draw_objects(draw, objects, room, bounds):
    """Small symbols are approximate anchors, never scaled obstacle footprints."""
    left, top, right, bottom = bounds
    labels = []
    for obj in objects:
        p = point(obj["xy"], room, bounds)
        if not p:
            continue
        x, y = p
        fresh = obj["visible"]
        color = "#4e6d80" if fresh else "#899297"
        draw.rectangle((x-7, y-7, x+7, y+7), fill="#d9e3e7" if fresh else MAP,
                       outline=color, width=2 if fresh else 1)
        if fresh:
            draw.line((x-3, y+2, x+3, y+2), fill=color, width=2)
        label = f"{obj['label']} {obj['identity']}"
        if not fresh:
            label += f" · {obj['age_s']:.0f}s ago"
        tw = draw.textlength(label, font=font(11))
        candidates = [(x+15, y-10), (x-tw-20, y-10), (x+15, y+13), (x-tw/2, y-35)]
        for tx, ty in candidates:
            tx, ty = max(left+6, min(right-tw-10, tx)), max(top+4, min(bottom-25, ty))
            box = (tx-4, ty-2, tx+tw+5, ty+19)
            if all(box[2] < a or box[0] > c or box[3] < b or box[1] > d for a, b, c, d in labels):
                labels.append(box)
                draw.rectangle(box, fill=PAPER)
                text(draw, (tx, ty), label, 11, color)
                break


def draw_floorplan(draw, views, room, stereo, state, radar_points, radar_status):
    # Equal scale in both axes: the room proportions remain meaningful.
    scale = min(588/room[0], 398/room[1])
    w, h = room[0]*scale, room[1]*scale
    left, top = 419-w/2, 192+(398-h)/2
    right, bottom = left+w, top+h
    bounds = (left, top, right, bottom)
    draw.rectangle(bounds, fill=MAP)
    grid = "#dedbd2"
    for gx in np.arange(1, room[0], 1):
        px, _ = point((float(gx), 0), room, bounds)
        draw.line((px, top, px, bottom), fill=grid)
    for gy in np.arange(1, room[1], 1):
        _, py = point((0, float(gy)), room, bounds)
        draw.line((left, py, right, py), fill=grid)
    # Crisp perimeter and architectural corner extensions.
    draw.rectangle(bounds, outline="#767b70", width=2)
    for x in (left, right):
        for y in (top, bottom):
            draw.line((x-6, y, x+6, y), fill=INK)
            draw.line((x, y-6, x, y+6), fill=INK)
    for gy in np.arange(0, room[1]+.001, 1):
        p = point((0, float(gy)), room, bounds)
        text(draw, (left-19, p[1]), f"{gy:g}", 11, FAINT, anchor="rm")
    for gx in np.arange(0, room[0]+.001, 1):
        p = point((float(gx), 0), room, bounds)
        text(draw, (p[0], bottom+14), f"{gx:g}", 11, FAINT, anchor="mt")
    text(draw, (left-19, top-23), "m", 11, FAINT, anchor="rm")
    text(draw, ((left+right)/2, top-25), f"{room[0]:g} m", 12, MUTED, anchor="mm")
    text(draw, (right+23, (top+bottom)/2), f"{room[1]:g} m", 12, MUTED, anchor="lm")

    path = list(stereo["target"].trail)[-160:]
    for i, (a, b) in enumerate(zip(path, path[1:])):
        pa, pb = point(a, room, bounds), point(b, room, bounds)
        if pa and pb:
            fade = .20+.70*(i+1)/max(1, len(path)-1)
            color = tuple(round(lo+(hi-lo)*fade) for lo, hi in zip((238, 236, 229), (173, 79, 53)))
            draw.line((pa, pb), fill=color, width=3)

    # Camera and radar symbols use their configured origins; no target association.
    for view in views:
        p = point(view.pose[:2], room, bounds)
        if p:
            x, y = p
            draw.rectangle((x-5, y-3, x+5, y+3), fill=BLUE)
            draw.polygon(((x-3, y-4), (x+3, y-4), (x, y-9)), fill=BLUE)
    radar_pose = stereo.get("radar_pose", (room[0]/2, 0, 0))
    if radar_status != "NOT CONNECTED":
        p = point(radar_pose[:2], room, bounds)
        if p:
            draw.rectangle((p[0]-3, p[1]-3, p[0]+3, p[1]+3), fill=INK)
    text(draw, (right+23, bottom), "Sensor wall", 10, MUTED, anchor="lm")
    draw_objects(draw, stereo.get("objects", []), room, bounds)

    radar_mode = stereo.get("position_source") == "radar"
    shown = [] if radar_mode and state["live"] and len(radar_points) == 1 else radar_points
    outside = 0
    for xy in shown:
        p = point(xy, room, bounds)
        if not p:
            outside += 1
    if state["live"]:
        p = point(stereo["target"].xy, room, bounds)
        if p:
            x, y = p
            draw.ellipse((x-22, y-22, x+22, y+22), fill="#e4c9ba", outline="#c99782")
            draw.ellipse((x-10, y-10, x+10, y+10), fill=ACCENT)
            dot(draw, x, y, PAPER, 3)
            label = "Person" if radar_mode else "You"
            tw = draw.textlength(label, font=font(13, True))
            tx = min(right-tw-18, max(left+10, x+30))
            ty = min(bottom-32, max(top+8, y-13))
            draw.rectangle((tx-7, ty-4, tx+tw+9, ty+23), fill=PAPER)
            text(draw, (tx, ty), label, 13, INK, True)
        else:
            text(draw, ((left+right)/2, top+26), "Position outside room view", 15, GOLD, anchor="mm")
    elif not stereo.get("map_objects"):
        cx, cy = (left+right)/2, (top+bottom)/2
        tw = max(draw.textlength(state["heading"], font=font(20, family="serif")),
                 draw.textlength(state["helper"], font=font(12)))
        draw.rectangle((cx-tw/2-22, cy-43, cx+tw/2+22, cy+43), fill=PAPER)
        text(draw, (cx, cy-14), state["heading"], 20, INK, anchor="mm", family="serif")
        text(draw, (cx, cy+20), state["helper"], 12, MUTED, anchor="mm")
    # Keep separate radar observations visible even beside a stereo position or
    # beneath a waiting prompt. Never shift them to make the layout cleaner.
    for xy in shown:
        p = point(xy, room, bounds)
        if p:
            x, y = p
            draw.polygon(((x, y-6), (x+6, y), (x, y+6), (x-6, y)), fill=GOLD)
    return outside


def draw_details(draw, stereo, views, state, now, radar_status, room):
    # A paper inset replaces the floorplan; the right-hand live views remain visible.
    draw.rectangle((32, 142, 802, 644), fill=PAPER, outline=LINE)
    caps(draw, (56, 164), "System / observation details")
    text(draw, (56, 190), "Behind the measurement", 27, family="serif")
    text(draw, (778, 167), "D to return", 12, MUTED, anchor="ra")
    age = now-stereo["target"].updated
    radar_mode = stereo.get("position_source") == "radar"
    metrics = [
        ("Camera devices · left / right", " / ".join(str(v.index) for v in views)),
        ("Latest valid position", f"{age:.2f} s ago" if math.isfinite(age) and age >= 0 else "Not received"),
        ("Image match support", f"{stereo['support_fraction']:.0%}" if state["live"] and stereo.get("support_fraction") is not None else "—"),
        ("Host frame-time difference", f"{stereo['skew_ms']:.1f} ms" if state["live"] and stereo.get("skew_ms") is not None else "—"),
        ("Calibration", "Limited coverage · check distances" if stereo.get("calibration_warning") else "Geometric checks passed"),
        ("Room alignment", "Measured floor points" if stereo.get("room_aligned") else "Level camera axes assumed"),
        ("Radar", radar_status),
    ]
    if radar_mode:
        pose = stereo.get("radar_pose", (room[0]/2, 0, 0))
        metrics = [metrics[0], ("Position source", "LD2450 radar"), metrics[1],
                   ("Camera processing", "Original images · no stereo crop"),
                   ("Camera detections", "Independent · no identity matching"),
                   ("Radar placement · x / y / angle", f"{pose[0]:.2f} m / {pose[1]:.2f} m / {pose[2]:g}°"),
                   ("Radar", radar_status)]
        if stereo.get("map_objects"):
            metrics[3] = ("Object mapping · left", getattr(views[0], "object_status", ""))
            metrics[4] = ("Object mapping · right", getattr(views[1], "object_status", ""))
    for i, (name, value) in enumerate(metrics):
        y = 254+i*44
        draw.line((56, y-10, 778, y-10), fill=LINE)
        text(draw, (56, y), name, 13, MUTED)
        fit_text(draw, (348, y), value, 427, 14)
    details_note = "Objects: approximate floor anchors; remembered for 12s. No size/height measured." if stereo.get("map_objects") else stereo.get("status", "")
    fit_text(draw, (56, 602), details_note, 715, 12, MUTED)


def render(views, *, now, room, stereo, radar_points=(), radar_status="NOT CONNECTED",
           recording=False, preview=False, size=(1280, 720)):
    width, height = size
    if width < 640 or height < 360 or width*9 != height*16:
        raise ValueError("Dashboard size must be 16:9 and at least 640x360.")
    canvas = Image.new("RGB", size, BG)
    draw = DensityDraw(canvas, width/1280)
    state = presentation(stereo, views, now, room)
    radar_mode = stereo.get("position_source") == "radar"
    radar_points = radar_points if (radar_status.startswith("LIVE") or
                                    (preview and radar_status == "PREVIEW ONLY")) else []

    # Masthead: quiet branding and a plain, honest session indicator.
    draw.line((32, 24, 32, 44), fill=ACCENT, width=3)
    caps(draw, (45, 22), "Kogane", INK, size=16, spacing=3)
    draw.line((180, 25, 180, 43), fill=LINE)
    caps(draw, (197, 27), "Spatial observatory", size=10, spacing=2)
    elapsed = max(0, int(stereo.get("elapsed_s", 0)))
    session = "EXAMPLE DATA / LAYOUT PREVIEW" if preview else (
        f"REC   {elapsed//60:02}:{elapsed%60:02}" if recording else "LIVE SESSION")
    session_color = GOLD if preview else RED if recording else TEAL
    sw = draw.textlength(session, font=font(11, True))
    dot(draw, 1248-sw-17, 34, session_color, 3)
    text(draw, (1248, 26), session, 11, session_color, True, anchor="ra")
    draw.line((32, 62, 1248, 62), fill=LINE)
    text(draw, (32, 77), "A room in motion.", 37, family="serif")
    text(draw, (1248, 91), ("RADAR POSITION  /  CAMERA OBJECT MAP" if stereo.get("map_objects") else
                          "RADAR POSITION  /  DUAL CAMERA COVERAGE") if radar_mode else
         "STEREO POSITION  /  ROOM RADAR", 10, MUTED, anchor="ra")
    draw.line((814, 142, 814, 642), fill=LINE)

    caps(draw, (32, 143), "01 / Floor plan")
    text(draw, (788, 141), f"{room[0]:g} × {room[1]:g} m   /   TOP VIEW", 11, MUTED, anchor="ra")
    if stereo.get("map_objects"):
        objects = stereo.get("objects", [])
        remembered = sum(not obj["visible"] for obj in objects)
        summary = f"{len(objects)} mapped objects" + (f" · {remembered} last seen" if remembered else "")
        text(draw, (788, 162), summary, 11, BLUE, anchor="ra")
    outside = draw_floorplan(draw, views, room, stereo, state, radar_points, radar_status)
    dot(draw, 38, 636, ACCENT, 4)
    text(draw, (51, 627), "Radar position" if radar_mode else "Stereo position", 11, MUTED)
    draw.line((180, 636, 201, 636), fill=ACCENT, width=2)
    text(draw, (211, 627), "Walking path", 11, MUTED)
    draw.polygon(((325, 631), (330, 636), (325, 641), (320, 636)), fill=GOLD)
    text(draw, (338, 627), "Other detections" if radar_mode else "Radar detections", 11, MUTED)
    if stereo.get("map_objects"):
        draw.rectangle((475, 631, 484, 640), outline="#4e6d80", width=2)
        text(draw, (494, 627), "Camera object", 11, MUTED)
    if outside:
        text(draw, (788, 627), f"{outside} detection(s) outside view", 11, GOLD, anchor="ra")

    # The main reading has generous space and a clear typographic hierarchy.
    caps(draw, (846, 143), "02 / Live position")
    value = f"{state['depth']:.1f}" if state["depth"] is not None else "—"
    text(draw, (842, 161), value, 86, family="number")
    vw = draw.textlength(value, font=font(86, family="number"))
    if state["depth"] is not None:
        text(draw, (854+vw, 210), "m", 25, MUTED, family="serif")
    text(draw, (846, 257), "Distance from radar" if radar_mode else "Depth from cameras", 14, MUTED)
    draw.line((846, 292, 1248, 292), fill=LINE)
    caps(draw, (846, 307), "Across the room", size=9, spacing=1.1)
    caps(draw, (1061, 307), "Into the room", size=9, spacing=1.1)
    text(draw, (846, 326), state["lateral"], 17)
    # The value is already qualified by its column heading.
    forward = state["forward"].replace(" into room", "")
    text(draw, (1061, 326), forward, 17)
    dot(draw, 850, 373, TEAL if state["live"] else GOLD, 3)
    text(draw, (863, 363), state["heading"], 13, TEAL if state["live"] else GOLD)
    draw.line((846, 400, 1248, 400), fill=LINE)

    for view, box, title in zip(views, ((846, 420, 1039, 611), (1055, 420, 1248, 611)),
                                ("Left view", "Right view")):
        draw_camera(canvas, draw, view, box, title, now)
    radar_label, radar_color, _ = radar_message(radar_status, radar_points)
    caps(draw, (846, 627), "Radar", size=9, spacing=1.2)
    text(draw, (1248, 623), radar_label, 12, radar_color, anchor="ra")

    # Provenance stays visible on both live and enlarged-camera layouts.
    if radar_mode:
        note = "Position from configured radar placement. Camera detections are independent."
        if stereo.get("map_objects"):
            note = "Objects: approximate floor anchors, not measured footprints. Outlined / 'ago' = last seen."
    else:
        note = "Room placement aligned to floor points." if stereo.get("room_aligned") else "Approximate room placement."
        if stereo.get("calibration_warning"):
            note += " Demo calibration: check measured distances."
    if preview:
        note = "Layout preview with example data. No live sensor readings are shown."
    draw.line((32, 659, 1248, 659), fill=LINE)
    text(draw, (32, 667), note, 11, MUTED)
    commands = [("F", "Fullscreen"), ("V", "Camera views"), ("D", "Details"), ("C", "Clear path")]
    if stereo.get("map_objects"):
        commands.append(("O", "Clear objects"))
    if not radar_mode:
        commands.append(("L", "Unlock" if stereo.get("locked") else "Lock person"))
    commands.append(("Q", "Save & close" if recording else "Close"))
    x = 32
    for key, meaning in commands:
        text(draw, (x, 695), key, 10, INK, True)
        text(draw, (x+17, 694), meaning, 10, MUTED)
        x += 17+draw.textlength(meaning, font=font(10))+25
    text(draw, (1248, 694), "KOGANE   /   ROOM OBSERVATION", 9, FAINT, anchor="ra")

    if stereo.get("show_cameras"):
        draw.rectangle((32, 138, 1248, 646), fill=BG)
        for view, box, title in zip(views, ((32, 146, 628, 640), (652, 146, 1248, 640)),
                                    ("01 / Left camera — full image", "02 / Right camera — full image")):
            draw_camera(canvas, draw, view, box, title, now)
    if stereo.get("show_details"):
        draw_details(draw, stereo, views, state, now, radar_status, room)
    return np.asarray(canvas)[:, :, ::-1].copy()
