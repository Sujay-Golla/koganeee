"""HLK-LD2450 report-frame decoder. Pure bytes in, targets out — no serial I/O.

This is the Python mirror of `firmware/mmwave-node-esp32c3/main/ld2450.c`. It exists because
the project BOM has no ESP32-C3: the radar is wired straight to the laptop through a 3.3 V
USB-UART adapter, so the laptop has to parse the radar's own UART protocol itself. The serial
port lives in `tracking/radar.py`; everything here is a pure function of bytes and is unit
tested without hardware.

Report frame (30 bytes, 256000 8N1, ~10 Hz):

    AA FF 03 00 | target0[8] | target1[8] | target2[8] | 55 CC
    ^ header      ^ x,y,speed,resolution (4 × u16 little-endian)      ^ footer

There is no checksum, so the footer is the only integrity check available. Frames are fixed
length, which is what makes resynchronisation on garbage tractable.

Sign encoding — the one thing worth getting right
-------------------------------------------------
x, y and speed are **sign-magnitude**, not two's complement. Bit 15 is a sign *flag* and the
low 15 bits are the magnitude:

    bit15 = 1  ->  +magnitude
    bit15 = 0  ->  -magnitude

So 0x81F4 is +500 mm and 0x01F4 is -500 mm. Reading the field as a plain little-endian `int16`
gives -32268 and +500 respectively — both wrong. `resolution` is an ordinary unsigned u16.

Provenance: this matches ESPHome's `ld2450` component (`decode_coordinate`/`decode_speed`,
which mask `0x7FFF` and negate when the top bit is clear) and the C mirror in this repo. Note
that some third-party libraries on GitHub implement the *opposite* polarity; ESPHome's is the
widely-deployed reading of the HLK-LD2450 serial protocol datasheet and is what we follow.
**This has not been checked against bytes from a physical module** — if a real LD2450 ever
reports a target mirrored about the sensor's boresight, flip the comparison in
`decode_signed` and nothing else needs to change.

Speed is reported in cm/s, which is already the unit `mmwave_targets` uses in PROTOCOL.md, so
no scaling happens here.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable

HEADER = b"\xaa\xff\x03\x00"
FOOTER = b"\x55\xcc"
MAX_TARGETS = 3
TARGET_LEN = 8
FRAME_LEN = len(HEADER) + MAX_TARGETS * TARGET_LEN + len(FOOTER)  # 30

# Four little-endian u16s; the sign-magnitude decode happens after unpacking.
_RAW_TARGET = struct.Struct("<HHHH")

# Ceiling on the resync buffer. The parse loop already keeps the buffer under one frame
# (see `Ld2450Parser.feed`), so this only ever fires if that invariant is broken.
_MAX_BUFFER = 4 * FRAME_LEN


@dataclass(frozen=True)
class Target:
    """One tracked target in the *sensor's* frame: +x right, +y away from the board."""

    x_mm: int
    y_mm: int
    speed_cms: int
    resolution_mm: int

    def as_payload_tuple(self) -> tuple[int, int, int, int]:
        """Field order used by `protocol.pack_mmwave` / `protocol.parse_mmwave`."""
        return (self.x_mm, self.y_mm, self.speed_cms, self.resolution_mm)


def decode_signed(raw: int) -> int:
    """Sign-magnitude u16 -> int. Bit 15 set means positive. See the module docstring."""
    magnitude = raw & 0x7FFF
    return magnitude if raw & 0x8000 else -magnitude


def encode_signed(value: int) -> int:
    """Inverse of `decode_signed`. For building synthetic frames (tests, simulator)."""
    magnitude = abs(int(value))
    if magnitude > 0x7FFF:
        raise ValueError(f"magnitude {magnitude} does not fit in 15 bits")
    return (0x8000 | magnitude) if value >= 0 else magnitude


def decode_target(raw: bytes) -> Target | None:
    """Decode one 8-byte slot. Returns None for an unoccupied slot.

    Emptiness test mirrors `ld2450.c`: x, y and speed all zero. Resolution is excluded
    because an idle module leaves stale resolution bytes in an otherwise empty slot on some
    firmwares. A genuinely all-zero slot satisfies this too, which is the convention
    `tracking.mmwave.detections_from_payload` already assumes downstream.
    """
    if len(raw) != TARGET_LEN:
        raise ValueError(f"target slot must be {TARGET_LEN} bytes, got {len(raw)}")
    rx, ry, rv, rres = _RAW_TARGET.unpack(raw)
    if rx == 0 and ry == 0 and rv == 0:
        return None
    return Target(decode_signed(rx), decode_signed(ry), decode_signed(rv), rres)


def encode_target(target: Target | None) -> bytes:
    """Inverse of `decode_target`; None produces an empty slot. Tests/simulator only."""
    if target is None:
        return bytes(TARGET_LEN)
    return _RAW_TARGET.pack(
        encode_signed(target.x_mm),
        encode_signed(target.y_mm),
        encode_signed(target.speed_cms),
        target.resolution_mm & 0xFFFF,
    )


def decode_report(frame: bytes) -> list[Target] | None:
    """Decode a complete 30-byte report frame. None if length/header/footer are wrong.

    Empty slots are dropped, so an idle radar decodes to `[]` — which is a valid report,
    not a failure. Callers must distinguish `[]` from `None`.
    """
    if len(frame) != FRAME_LEN:
        return None
    if not frame.startswith(HEADER) or not frame.endswith(FOOTER):
        return None
    return _decode_slots(frame)


def encode_report(targets: Iterable[Target | None]) -> bytes:
    """Build a 30-byte report frame. Tests and the simulator only, never the radar path."""
    slots = list(targets)
    if len(slots) > MAX_TARGETS:
        raise ValueError(f"LD2450 reports at most {MAX_TARGETS} targets, got {len(slots)}")
    slots += [None] * (MAX_TARGETS - len(slots))
    return HEADER + b"".join(encode_target(t) for t in slots) + FOOTER


def _decode_slots(frame: bytes) -> list[Target]:
    out: list[Target] = []
    for i in range(MAX_TARGETS):
        off = len(HEADER) + i * TARGET_LEN
        target = decode_target(frame[off:off + TARGET_LEN])
        if target is not None:
            out.append(target)
    return out


class Ld2450Parser:
    """Incremental parser for the LD2450 byte stream.

    `serial.read()` returns whatever happens to be in the OS buffer, so frames arrive split
    at arbitrary offsets and a hot-plug or a baud mismatch delivers pure garbage. `feed`
    therefore accepts any chunk size, resynchronises on the header, validates the footer,
    and returns the reports it could complete.

    Memory safety: after every `feed` the retained buffer is smaller than one frame. Either
    a header was found and the remainder is an incomplete frame (< 30 bytes), or no header
    was found and only the ≤ 3 bytes that could be a split header are kept. So garbage can
    never grow the buffer, regardless of how much of it arrives.
    """

    def __init__(self, max_buffer: int = _MAX_BUFFER) -> None:
        if max_buffer < FRAME_LEN:
            raise ValueError(f"max_buffer must be at least one frame ({FRAME_LEN} bytes)")
        self._max_buffer = int(max_buffer)
        self._buf = bytearray()
        # Counters, for logging a link that is delivering bytes but not frames.
        self.frames_decoded = 0
        self.bad_footers = 0
        self.bytes_discarded = 0

    @property
    def pending_bytes(self) -> int:
        """Bytes held over for the next `feed`. Always < FRAME_LEN once `feed` returns."""
        return len(self._buf)

    def reset(self) -> None:
        """Drop buffered bytes. Use after reopening the port, not between reads."""
        self._buf.clear()

    def feed(self, chunk: bytes) -> list[list[Target]]:
        """Consume bytes; return zero or more decoded reports, oldest first."""
        if chunk:
            self._buf += chunk

        reports: list[list[Target]] = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                self._keep_header_prefix()
                break
            if start > 0:
                self._discard(start)
            if len(self._buf) < FRAME_LEN:
                break                         # header seen, waiting for the rest
            if self._buf[FRAME_LEN - 2:FRAME_LEN] == FOOTER:
                reports.append(_decode_slots(bytes(self._buf[:FRAME_LEN])))
                self.frames_decoded += 1
                del self._buf[:FRAME_LEN]
            else:
                # Not a frame after all: the header bytes appeared inside noise, or bytes
                # were dropped mid-frame. Step over one byte so a real header further in
                # (possibly overlapping this one) is still found.
                self.bad_footers += 1
                self._discard(1)

        self._enforce_cap()
        return reports

    # ---- buffer housekeeping ----
    def _discard(self, n: int) -> None:
        del self._buf[:n]
        self.bytes_discarded += n

    def _keep_header_prefix(self) -> None:
        """No full header in the buffer: keep only a suffix that could be a split header."""
        keep = 0
        for n in range(min(len(HEADER) - 1, len(self._buf)), 0, -1):
            if self._buf[-n:] == HEADER[:n]:
                keep = n
                break
        drop = len(self._buf) - keep
        if drop > 0:
            self._discard(drop)

    def _enforce_cap(self) -> None:
        excess = len(self._buf) - self._max_buffer
        if excess > 0:
            # Unreachable given the loop's invariant; kept so a future change to the loop
            # cannot turn into unbounded growth on a misbehaving device.
            self._discard(excess)
