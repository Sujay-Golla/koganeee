"""Python mirror of firmware/shared/PROTOCOL.md (KGN UDP datagram)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"KGN"
VERSION = 1

# header: 3s magic, B version, B type, B flags, H seq, I src_id, H len
_HDR = struct.Struct("<3sBBBHIH")
HEADER_LEN = _HDR.size  # 14


class MsgType(IntEnum):
    MMWAVE_TARGETS = 0x01
    SETPOINT = 0x10
    MODE_CMD = 0x11
    DRONE_STATE = 0x20
    SCREEN_FRAME = 0x30
    AUDIO_TTS = 0x40
    AUDIO_MIC = 0x41
    HEARTBEAT = 0x7F


class CtrlMode(IntEnum):
    HOLD = 0
    VELOCITY = 1
    POSITION = 2


class Mode(IntEnum):
    """`mode_cmd` payload values."""

    IDLE = 0
    ARM = 1
    TAKEOFF = 2
    FOLLOW = 3
    LAND = 4
    DOCK = 5
    FAILSAFE = 6


class Role(IntEnum):
    """`heartbeat` role field."""

    BASE = 0
    DRONE = 1
    NODE = 2


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def pack(msg_type: int, payload: bytes, seq: int = 0, src_id: int = 0, flags: int = 0) -> bytes:
    hdr = _HDR.pack(MAGIC, VERSION, int(msg_type), flags, seq & 0xFFFF, src_id, len(payload))
    frame = hdr + payload
    return frame + struct.pack("<H", crc16_ccitt(frame))


@dataclass
class Frame:
    msg_type: int
    seq: int
    src_id: int
    payload: bytes


def unpack(data: bytes) -> Frame | None:
    if len(data) < HEADER_LEN + 2:
        return None
    magic, ver, mtype, flags, seq, src_id, plen = _HDR.unpack(data[:HEADER_LEN])
    if magic != MAGIC or ver != VERSION:
        return None
    if len(data) < HEADER_LEN + plen + 2:
        return None
    body_end = HEADER_LEN + plen
    (crc,) = struct.unpack("<H", data[body_end:body_end + 2])
    if crc != crc16_ccitt(data[:body_end]):
        return None
    return Frame(mtype, seq, src_id, data[HEADER_LEN:body_end])


# ---- payload (de)serializers ----
_TARGET = struct.Struct("<hhhH")  # x_mm, y_mm, speed_cms, res_mm


MMWAVE_TARGET_LEN = _TARGET.size  # 8


def pack_mmwave(targets) -> bytes:
    """Pack `mmwave_targets`: u8 count, then count × {i16 x_mm, i16 y_mm, i16 speed_cms,
    u16 res_mm}. Inverse of `parse_mmwave`; see PROTOCOL.md §1.

    `targets` is any iterable of 4-tuples in that field order. Used by the mmWave simulator
    and by loopback tests; the real node-side packing happens in the C firmware.
    """
    rows = list(targets)
    if len(rows) > 0xFF:
        raise ValueError(f"count is a u8; got {len(rows)} targets")
    out = bytearray()
    out.append(len(rows))
    for x_mm, y_mm, speed_cms, res_mm in rows:
        out += _TARGET.pack(x_mm, y_mm, speed_cms, res_mm)
    return bytes(out)


def parse_mmwave(payload: bytes) -> list[tuple[int, int, int, int]]:
    if not payload:
        return []
    count = payload[0]
    out = []
    off = 1
    for _ in range(count):
        if off + _TARGET.size > len(payload):
            break
        out.append(_TARGET.unpack(payload[off:off + _TARGET.size]))
        off += _TARGET.size
    return out


_SETPOINT = struct.Struct("<hhhhB")  # vx, vy, vz, yaw_rate, ctrl_mode
SETPOINT_LEN = _SETPOINT.size  # 9


def pack_setpoint(vx: int, vy: int, vz: int, yaw_rate: int, mode: CtrlMode) -> bytes:
    return _SETPOINT.pack(vx, vy, vz, yaw_rate, int(mode))


@dataclass
class Setpoint:
    vx_cms: int
    vy_cms: int
    vz_cms: int
    yaw_rate_cds: int
    ctrl_mode: int


def unpack_setpoint(payload: bytes) -> Setpoint | None:
    if len(payload) != SETPOINT_LEN:
        return None
    return Setpoint(*_SETPOINT.unpack(payload))


# drone_state: x_cm, y_cm, z_cm, yaw_cd, batt_mv, flags, link_q
_DRONE_STATE = struct.Struct("<hhhhHBB")
DRONE_STATE_LEN = _DRONE_STATE.size  # 12

# `drone_state.flags` — per-field validity bitmask (PROTOCOL.md §1). This is the *payload*
# byte at offset 10, not the header flags byte. A field whose bit is clear carries no data
# and its bytes are zero; that is not a measurement of zero, so check the bit before use.
DS_F_POS_VALID = 1 << 0     # x_cm, y_cm, z_cm are real
DS_F_YAW_VALID = 1 << 1     # yaw_cd is real
DS_F_BATT_VALID = 1 << 2    # batt_mv is real
DS_F_LINKQ_VALID = 1 << 3   # link_q is real
DS_F_FC_LINK_UP = 1 << 4    # companion is exchanging data with the flight controller
DS_F_ARMED = 1 << 5         # FC reports armed (implies FC_LINK_UP)


@dataclass
class DroneState:
    x_cm: int
    y_cm: int
    z_cm: int
    yaw_cd: int
    batt_mv: int
    flags: int
    link_q: int


def pack_drone_state(
    x_cm: int, y_cm: int, z_cm: int, yaw_cd: int, batt_mv: int, flags: int, link_q: int
) -> bytes:
    return _DRONE_STATE.pack(x_cm, y_cm, z_cm, yaw_cd, batt_mv, flags, link_q)


def unpack_drone_state(payload: bytes) -> DroneState | None:
    if len(payload) != DRONE_STATE_LEN:
        return None
    return DroneState(*_DRONE_STATE.unpack(payload))


# heartbeat: uptime_ms, role
_HEARTBEAT = struct.Struct("<IB")
HEARTBEAT_LEN = _HEARTBEAT.size  # 5


@dataclass
class Heartbeat:
    uptime_ms: int
    role: int


def pack_heartbeat(uptime_ms: int, role: Role) -> bytes:
    return _HEARTBEAT.pack(uptime_ms & 0xFFFFFFFF, int(role))


def unpack_heartbeat(payload: bytes) -> Heartbeat | None:
    if len(payload) != HEARTBEAT_LEN:
        return None
    return Heartbeat(*_HEARTBEAT.unpack(payload))


# mode_cmd: mode
_MODE_CMD = struct.Struct("<B")
MODE_CMD_LEN = _MODE_CMD.size  # 1


def pack_mode_cmd(mode: Mode) -> bytes:
    return _MODE_CMD.pack(int(mode))


def unpack_mode_cmd(payload: bytes) -> int | None:
    if len(payload) != MODE_CMD_LEN:
        return None
    (mode,) = _MODE_CMD.unpack(payload)
    return mode

# =====================================================================================
# screen_frame (0x30) — PROTOCOL.md §1 "screen_frame (0x30) — chunked panel updates"
# =====================================================================================
# The panel is an ILI9341 320x240 in landscape. Every 0x30 payload is
#   [8-byte sub-header][format-specific body]
# and each chunk is rendered on arrival: there is no reassembly buffer on the drone, so
# loss degrades to a missing tile rather than a dropped frame.

SCREEN_W = 320
SCREEN_H = 240

# The drone draws through one DMA band buffer of 320 x 32 px and rejects any tile that
# will not fit in it (display_spi.c: `want > BAND_PIXELS`).
SCREEN_BAND_PIXELS = 10240

# 1500 MTU - 28 IP/UDP - 14 KGN header - 2 crc - 8 sub-header - 8 tile header.
SCREEN_TILE_MAX_BODY = 1440
SCREEN_TILE_MAX_PIXELS = SCREEN_TILE_MAX_BODY // 2  # 720

# Text-mode grid: 10 rows of 24 px on a 240 px panel, 53 chars at the 6 px scale-1 cell.
SCREEN_TEXT_ROWS = 10
SCREEN_TEXT_ROW_PX = 24
SCREEN_TEXT_MAX = 53
# The drone clamps scale to SCREEN_TEXT_ROW_PX / 8, i.e. 3, so a row never spills into
# the next one. Anything larger is accepted on the wire and quietly clamped there.
SCREEN_TEXT_SCALE_MAX = 3


class ScreenFmt(IntEnum):
    """`screen_frame.fmt`."""

    RGB565 = 1
    TEXT = 2


# `screen_frame.flags`
SF_F_FIRST = 1 << 0    # clear the panel before applying this chunk
SF_F_LAST = 1 << 1     # last chunk of this frame
SF_F_STATUS = 1 << 2   # hand the panel back to the drone's own status screen; body ignored

# sub-header: fmt, frame_id, chunk_idx, chunk_cnt, flags, reserved[3]
_SCREEN_HDR = struct.Struct("<BBBBB3s")
SCREEN_HDR_LEN = _SCREEN_HDR.size  # 8

# fmt=1 tile header: x, y, w, h
_SCREEN_TILE = struct.Struct("<HHHH")
SCREEN_TILE_LEN = _SCREEN_TILE.size  # 8

# fmt=2 line header: row, scale, fg, bg
_SCREEN_TEXT = struct.Struct("<BBHH")
SCREEN_TEXT_LEN = _SCREEN_TEXT.size  # 6


@dataclass
class ScreenHeader:
    fmt: int
    frame_id: int
    chunk_idx: int
    chunk_cnt: int
    flags: int


def pack_screen_header(fmt: int, frame_id: int = 0, chunk_idx: int = 0, chunk_cnt: int = 0,
                       flags: int = 0) -> bytes:
    """The 8-byte `screen_frame` sub-header. `reserved` is always three zero bytes."""
    return _SCREEN_HDR.pack(int(fmt) & 0xFF, frame_id & 0xFF, chunk_idx & 0xFF,
                            chunk_cnt & 0xFF, flags & 0xFF, b"\x00\x00\x00")


def unpack_screen_header(payload: bytes) -> ScreenHeader | None:
    """Parse the sub-header off the front of a 0x30 payload; None if it is too short."""
    if len(payload) < SCREEN_HDR_LEN:
        return None
    fmt, frame_id, chunk_idx, chunk_cnt, flags, _res = _SCREEN_HDR.unpack(
        payload[:SCREEN_HDR_LEN])
    return ScreenHeader(fmt, frame_id, chunk_idx, chunk_cnt, flags)


@dataclass
class ScreenTile:
    x: int
    y: int
    w: int
    h: int
    pixels: bytes


def pack_screen_tile_header(x: int, y: int, w: int, h: int) -> bytes:
    """The 8-byte `fmt=1` tile header (no pixels)."""
    return _SCREEN_TILE.pack(x, y, w, h)


def check_tile_geometry(x: int, y: int, w: int, h: int) -> None:
    """Raise ValueError for a tile the drone would count and drop.

    Mirrors display_spi.c `handle_rgb565`: zero extent, running off either edge, or a
    tile bigger than the 320x32 band buffer. Better to fail here than to have the drone
    silently bump a dropped-chunk counter.
    """
    if w <= 0 or h <= 0:
        raise ValueError(f"tile must be non-empty; got w={w} h={h}")
    if x < 0 or y < 0:
        raise ValueError(f"tile origin must be non-negative; got x={x} y={y}")
    if x + w > SCREEN_W or y + h > SCREEN_H:
        raise ValueError(
            f"tile {w}x{h} at ({x}, {y}) runs off the {SCREEN_W}x{SCREEN_H} panel")
    if w * h > SCREEN_BAND_PIXELS:
        raise ValueError(
            f"tile is {w * h} px; the drone's band buffer holds {SCREEN_BAND_PIXELS}")


def screen_tile_payload(x: int, y: int, w: int, h: int, pixels: bytes, *,
                        frame_id: int = 0, chunk_idx: int = 0, chunk_cnt: int = 0,
                        flags: int = 0) -> bytes:
    """A complete `fmt=1` SCREEN_FRAME payload, ready for `pack(MsgType.SCREEN_FRAME, ...)`.

    `pixels` is `w*h` RGB565 little-endian samples, row-major, no padding — exactly what
    `rgb565_bytes` produces. Geometry and length are validated against what the drone
    accepts; a short body is a hard error because the drone would drop the chunk.
    """
    check_tile_geometry(x, y, w, h)
    want = w * h * 2
    if len(pixels) < want:
        raise ValueError(f"tile {w}x{h} needs {want} pixel bytes; got {len(pixels)}")
    if want > SCREEN_TILE_MAX_BODY:
        raise ValueError(
            f"tile body is {want} bytes; one datagram carries {SCREEN_TILE_MAX_BODY} "
            f"({SCREEN_TILE_MAX_PIXELS} px). Split it into strips.")
    return (pack_screen_header(ScreenFmt.RGB565, frame_id, chunk_idx, chunk_cnt, flags)
            + _SCREEN_TILE.pack(x, y, w, h) + bytes(pixels[:want]))


def unpack_screen_tile(payload: bytes) -> ScreenTile | None:
    """Parse a `fmt=1` body (sub-header included). None if short or not a tile."""
    hdr = unpack_screen_header(payload)
    if hdr is None or hdr.fmt != ScreenFmt.RGB565:
        return None
    body = payload[SCREEN_HDR_LEN:]
    if len(body) < SCREEN_TILE_LEN:
        return None
    x, y, w, h = _SCREEN_TILE.unpack(body[:SCREEN_TILE_LEN])
    px = body[SCREEN_TILE_LEN:]
    if len(px) < w * h * 2:
        return None
    return ScreenTile(x, y, w, h, px[:w * h * 2])


@dataclass
class ScreenTextLine:
    row: int
    scale: int
    fg: int
    bg: int
    text: str


def pack_screen_text_header(row: int, scale: int, fg: int, bg: int) -> bytes:
    """The 6-byte `fmt=2` line header (no text)."""
    return _SCREEN_TEXT.pack(row & 0xFF, scale & 0xFF, fg & 0xFFFF, bg & 0xFFFF)


def screen_text_sanitise(text: str) -> str:
    """Replace anything the drone's 5x7 font cannot draw with '?'.

    The drone already does this, so doing it here only makes the bytes on the wire say
    what will actually appear on the panel.
    """
    return "".join(c if 0x20 <= ord(c) <= 0x7E else "?" for c in text)


def screen_text_payload(text: str, row: int = 0, scale: int = 1,
                        fg: int = 0xFFFF, bg: int = 0x0000, *,
                        frame_id: int = 0, chunk_idx: int = 0, chunk_cnt: int = 0,
                        flags: int = 0) -> bytes:
    """A complete `fmt=2` SCREEN_FRAME payload.

    Strict on purpose: `text` must already be printable ASCII and within
    `SCREEN_TEXT_MAX`. Callers that want truncation should use
    `screen.sender.prepare_text`, which warns about what it cut. The text is **not**
    NUL-terminated on the wire.
    """
    if not 0 <= row < SCREEN_TEXT_ROWS:
        raise ValueError(f"row must be 0..{SCREEN_TEXT_ROWS - 1}; got {row}")
    if scale < 1:
        raise ValueError(f"scale must be >= 1; got {scale}")
    raw = text.encode("ascii", errors="strict")
    if len(raw) > SCREEN_TEXT_MAX:
        raise ValueError(f"text is {len(raw)} chars; the drone truncates at "
                         f"{SCREEN_TEXT_MAX}")
    if any(b < 0x20 or b > 0x7E for b in raw):
        raise ValueError("text must be printable ASCII 0x20..0x7E; "
                         "use screen_text_sanitise first")
    return (pack_screen_header(ScreenFmt.TEXT, frame_id, chunk_idx, chunk_cnt, flags)
            + _SCREEN_TEXT.pack(row, scale, fg & 0xFFFF, bg & 0xFFFF) + raw)


def unpack_screen_text(payload: bytes) -> ScreenTextLine | None:
    """Parse a `fmt=2` body (sub-header included). None if short or not a text line."""
    hdr = unpack_screen_header(payload)
    if hdr is None or hdr.fmt != ScreenFmt.TEXT:
        return None
    body = payload[SCREEN_HDR_LEN:]
    if len(body) < SCREEN_TEXT_LEN:
        return None
    row, scale, fg, bg = _SCREEN_TEXT.unpack(body[:SCREEN_TEXT_LEN])
    text = body[SCREEN_TEXT_LEN:].decode("ascii", errors="replace")
    return ScreenTextLine(row, scale, fg, bg, text)


def screen_status_payload(frame_id: int = 0) -> bytes:
    """A STATUS chunk: hands the panel straight back to the drone's own status screen.

    `fmt` still has to be something the drone will look at, but the body is ignored when
    SF_F_STATUS is set, so this is a bare 8-byte sub-header.
    """
    return pack_screen_header(ScreenFmt.TEXT, frame_id, 0, 1,
                              SF_F_STATUS | SF_F_FIRST | SF_F_LAST)


# ---- RGB565 ---------------------------------------------------------------------------
# 5 bits red in 15..11, 6 bits green in 10..5, 5 bits blue in 4..0. On the wire the u16 is
# little-endian (the drone byte-swaps on the way into its band buffer, because the ILI9341
# wants big-endian).
def rgb565(r: int, g: int, b: int) -> int:
    """Pack one 8-bit-per-channel colour into an RGB565 u16.

    >>> hex(rgb565(255, 0, 0)), hex(rgb565(0, 255, 0)), hex(rgb565(0, 0, 255))
    ('0xf800', '0x7e0', '0x1f')
    """
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)


RGB565_BLACK = 0x0000
RGB565_WHITE = 0xFFFF
RGB565_RED = 0xF800
RGB565_GREEN = 0x07E0
RGB565_BLUE = 0x001F
RGB565_CYAN = 0x07FF
RGB565_MAGENTA = 0xF81F
RGB565_YELLOW = 0xFFE0
RGB565_AMBER = 0xFD20     # 255,165,0
RGB565_GREY = 0x8410      # 128,128,128


def rgb565_bytes(rgb) -> bytes:
    """numpy RGB array -> little-endian RGB565 bytes, row-major, no padding.

    Accepts any shape whose last axis is 3 (so both an (h, w, 3) image and an (n, 3) run
    of pixels work) and returns exactly `2 * count` bytes, which is the `fmt=1` body.
    numpy is imported here rather than at module scope to keep the rest of this module
    stdlib-only.
    """
    import numpy as np

    a = np.asarray(rgb)
    if a.ndim < 1 or a.shape[-1] != 3:
        raise ValueError(f"expected an RGB array with last axis 3; got shape {a.shape}")
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    r = a[..., 0].astype(np.uint16)
    g = a[..., 1].astype(np.uint16)
    b = a[..., 2].astype(np.uint16)
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | ((b & 0xF8) >> 3)
    return v.astype("<u2").tobytes()


def rgb565_to_rgb(data: bytes, w: int, h: int):
    """Inverse of `rgb565_bytes` for inspection/tests: -> (h, w, 3) uint8 numpy array.

    Lossy in the obvious way (the dropped low bits come back as zeros), so compare
    against `rgb565_bytes(rgb565_to_rgb(...))` rather than against the original RGB.
    """
    import numpy as np

    want = w * h * 2
    if len(data) < want:
        raise ValueError(f"need {want} bytes for {w}x{h}; got {len(data)}")
    v = np.frombuffer(data[:want], dtype="<u2").reshape(h, w).astype(np.uint16)
    r = ((v >> 11) & 0x1F) << 3
    g = ((v >> 5) & 0x3F) << 2
    b = (v & 0x1F) << 3
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


# =====================================================================================
# audio_chunk (0x40 AUDIO_TTS, 0x41 AUDIO_MIC) — PROTOCOL.md §1
# =====================================================================================
# One layout for both directions. `fmt=1` is raw PCM at a rate that is part of the format
# rather than negotiated; `fmt=2` is a single control byte and is base -> drone only.

AUDIO_RATE_HZ = 16000          # fixed by the format, not negotiated
AUDIO_SAMPLE_WIDTH = 2         # signed 16-bit little-endian
AUDIO_CHANNELS = 1             # mono

# 1500 MTU - 28 IP/UDP - 14 KGN header - 2 crc - 4 sub-header = 1452, capped at 1440 for a
# whole number of 16-sample groups. 720 samples = 45 ms at 16 kHz.
AUDIO_PCM_MAX_BYTES = 1440
AUDIO_PCM_MAX_SAMPLES = AUDIO_PCM_MAX_BYTES // AUDIO_SAMPLE_WIDTH  # 720

# The drone's playback queue holds 12 chunks and drops the OLDEST on overflow, so a sender
# that outruns real time loses the *start* of what it sent. Senders must pace.
AUDIO_TTS_QUEUE_DEPTH = 12

# What the drone's mic task emits: 512 samples = 32 ms = a 1024-byte body.
AUDIO_MIC_BLOCK_SAMPLES = 512


class AudioFmt(IntEnum):
    """`audio_chunk.fmt`."""

    PCM_S16LE = 1
    CTRL = 2


class AudioCmd(IntEnum):
    """`fmt=2` command byte. Base -> drone only."""

    MIC_ON = 1
    MIC_OFF = 2
    SELFTEST = 3
    FLUSH = 4


# `audio_chunk.flags`
AU_F_START = 1 << 0   # first chunk of this utterance/stream; receiver flushes its backlog
AU_F_END = 1 << 1     # last chunk of this utterance/stream

# sub-header: fmt, flags, seq. 4 bytes so the PCM body lands 2-byte aligned.
_AUDIO_HDR = struct.Struct("<BBH")
AUDIO_HDR_LEN = _AUDIO_HDR.size  # 4


@dataclass
class AudioHeader:
    fmt: int
    flags: int
    seq: int


def pack_audio_header(fmt: int, flags: int = 0, seq: int = 0) -> bytes:
    """The 4-byte `audio_chunk` sub-header."""
    return _AUDIO_HDR.pack(int(fmt) & 0xFF, flags & 0xFF, seq & 0xFFFF)


def unpack_audio_header(payload: bytes) -> AudioHeader | None:
    if len(payload) < AUDIO_HDR_LEN:
        return None
    fmt, flags, seq = _AUDIO_HDR.unpack(payload[:AUDIO_HDR_LEN])
    return AudioHeader(fmt, flags, seq)


def audio_pcm_payload(pcm: bytes, seq: int = 0, flags: int = 0) -> bytes:
    """A complete `fmt=1` audio payload, ready for `pack(MsgType.AUDIO_TTS, ...)`.

    `pcm` is raw signed-16 little-endian mono at `AUDIO_RATE_HZ`. Validated against what
    the drone accepts (audio_i2s.c: non-empty, whole samples, <= 1440 bytes) so an
    oversized chunk fails here instead of being counted and dropped on the aircraft.
    """
    n = len(pcm)
    if n == 0:
        raise ValueError("empty PCM chunk; the drone drops these")
    if n % AUDIO_SAMPLE_WIDTH:
        raise ValueError(f"PCM body must be whole int16 samples; got {n} bytes")
    if n > AUDIO_PCM_MAX_BYTES:
        raise ValueError(f"PCM body is {n} bytes; the drone drops anything over "
                         f"{AUDIO_PCM_MAX_BYTES} ({AUDIO_PCM_MAX_SAMPLES} samples)")
    return pack_audio_header(AudioFmt.PCM_S16LE, flags, seq) + bytes(pcm)


def audio_ctrl_payload(cmd: AudioCmd | int, seq: int = 0, flags: int = 0) -> bytes:
    """A complete `fmt=2` audio payload: the sub-header plus one command byte."""
    c = int(cmd)
    if not 0 <= c <= 0xFF:
        raise ValueError(f"cmd is a u8; got {c}")
    return pack_audio_header(AudioFmt.CTRL, flags, seq) + bytes((c,))


@dataclass
class AudioChunk:
    """A decoded 0x40/0x41 payload. Exactly one of `pcm` / `cmd` is set."""

    fmt: int
    flags: int
    seq: int
    pcm: bytes | None = None
    cmd: int | None = None

    @property
    def start(self) -> bool:
        return bool(self.flags & AU_F_START)

    @property
    def end(self) -> bool:
        return bool(self.flags & AU_F_END)

    @property
    def samples(self) -> int:
        return 0 if self.pcm is None else len(self.pcm) // AUDIO_SAMPLE_WIDTH

    @property
    def duration_s(self) -> float:
        return self.samples / AUDIO_RATE_HZ


def unpack_audio_chunk(payload: bytes) -> AudioChunk | None:
    """Decode an inbound 0x41 (or 0x40) payload. None for anything the drone would drop.

    Applies the same acceptance rules as the firmware: whole int16 samples only, body
    within `AUDIO_PCM_MAX_BYTES`, one byte for CTRL, unknown `fmt` rejected.
    """
    hdr = unpack_audio_header(payload)
    if hdr is None:
        return None
    body = payload[AUDIO_HDR_LEN:]
    if hdr.fmt == AudioFmt.PCM_S16LE:
        if not body or len(body) % AUDIO_SAMPLE_WIDTH or len(body) > AUDIO_PCM_MAX_BYTES:
            return None
        return AudioChunk(hdr.fmt, hdr.flags, hdr.seq, pcm=bytes(body))
    if hdr.fmt == AudioFmt.CTRL:
        if len(body) < 1:
            return None
        return AudioChunk(hdr.fmt, hdr.flags, hdr.seq, cmd=body[0])
    return None
