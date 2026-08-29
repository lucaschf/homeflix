"""Parser for HDMV PGS (Presentation Graphic Stream) subtitles.

PGS is the bitmap subtitle format carried on Blu-ray and, muxed, in many
MKV remuxes (ffmpeg codec ``hdmv_pgs_subtitle``). A ``.sup`` file — or a
demuxed PGS elementary stream — is a flat sequence of *segments*; a run
of segments terminated by an END segment forms a *display set* that
either shows a subtitle (a composition with objects) or clears the
previous one (an empty composition).

This module turns that byte stream into timed bitmaps
(:class:`PgsCue`): it decodes each object's RLE-compressed, palette-index
pixels, maps them through the YCbCr palette to RGBA, and pairs each
"show" set with the following "clear" set to recover cue timing. The
result feeds an OCR step (see :mod:`subtitle_ocr_service`); this module
itself is pure — only Pillow, no ffmpeg or tesseract — so it is fully
unit-testable from synthetic byte streams.

Reference: the PGS/SUP segment layout is documented at
https://blog.thescorpius.com/index.php/2017/07/15/presentation-graphic-stream-sup-files-bluray-subtitle-format/
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from collections.abc import Iterator

_MAGIC = b"PG"
_HEADER_LEN = 13  # magic(2) + pts(4) + dts(4) + type(1) + size(2)

# Segment type identifiers.
_SEG_PDS = 0x14  # Palette Definition Segment
_SEG_ODS = 0x15  # Object Definition Segment (the RLE bitmap)
_SEG_PCS = 0x16  # Presentation Composition Segment
_SEG_WDS = 0x17  # Window Definition Segment
_SEG_END = 0x80  # End of display set

# ODS sequence flags (an object may span several ODS segments).
_ODS_FIRST = 0x80
_ODS_LAST = 0x40

_PTS_HZ = 90_000  # PGS timestamps are in a 90 kHz clock.


@dataclass(frozen=True)
class PgsCue:
    """A single subtitle occurrence: its bitmap and on-screen timing.

    Attributes:
        start_ms: When the subtitle appears, in milliseconds.
        end_ms: When it is cleared, in milliseconds. Always greater than
            ``start_ms`` for cues returned by :func:`parse_pgs`.
        image: The rendered subtitle as an ``RGBA`` image (transparent
            background, coloured glyphs) ready for OCR preprocessing.
    """

    start_ms: int
    end_ms: int
    image: Image.Image


@dataclass
class _Segment:
    pts: int
    type: int
    data: bytes


def _iter_segments(raw: bytes) -> Iterator[_Segment]:
    """Yield each :class:`_Segment` from a raw PGS/SUP byte stream.

    Raises:
        ValueError: If a segment does not start with the ``PG`` magic,
            i.e. the stream is not PGS or is misaligned/truncated.
    """
    off = 0
    n = len(raw)
    while off + _HEADER_LEN <= n:
        if raw[off : off + 2] != _MAGIC:
            msg = f"Not a PGS stream: bad magic at offset {off}"
            raise ValueError(msg)
        pts = struct.unpack(">I", raw[off + 2 : off + 6])[0]
        seg_type = raw[off + 10]
        seg_size = struct.unpack(">H", raw[off + 11 : off + 13])[0]
        payload = raw[off + _HEADER_LEN : off + _HEADER_LEN + seg_size]
        off += _HEADER_LEN + seg_size
        yield _Segment(pts=pts, type=seg_type, data=payload)


def _parse_palette(data: bytes) -> dict[int, tuple[int, int, int, int]]:
    """Decode a PDS payload into ``{palette_index: (R, G, B, A)}``.

    Palette entries are stored as YCbCr + alpha; they are converted to
    RGBA with the BT.601 coefficients (PGS is standard-definition-derived).
    """
    palette: dict[int, tuple[int, int, int, int]] = {}
    # data[0]=palette id, data[1]=version, then 5-byte entries.
    body = data[2:]
    for i in range(0, len(body) - 4, 5):
        idx, y, cr, cb, alpha = body[i : i + 5]
        c = y - 16
        d = cb - 128
        e = cr - 128
        r = max(0, min(255, round(1.164 * c + 1.596 * e)))
        g = max(0, min(255, round(1.164 * c - 0.392 * d - 0.813 * e)))
        b = max(0, min(255, round(1.164 * c + 2.017 * d)))
        palette[idx] = (r, g, b, alpha)
    return palette


@dataclass
class _ObjectDef:
    obj_id: int
    width: int
    height: int
    rle: bytes = b""


def _decode_rle(rle: bytes, width: int, height: int) -> bytearray:
    """Decode PGS run-length data into a ``width * height`` index buffer.

    The PGS RLE encoding (per the format spec): a non-zero byte is a
    single pixel of that palette index; a zero byte introduces a run
    whose length and colour are encoded in the following one or two
    bytes, with ``0x00 0x00`` marking end-of-line (padding to the next
    row boundary).
    """
    out = bytearray(width * height)
    pos = 0
    i = 0
    n = len(rle)
    while i < n:
        first = rle[i]
        i += 1
        if first != 0:
            if pos < len(out):
                out[pos] = first
            pos += 1
            continue
        if i >= n:
            break
        second = rle[i]
        i += 1
        if second == 0:
            if width:  # end of line: pad to the row boundary
                pos += (width - (pos % width)) % width
            continue
        run_len = second & 0x3F
        if second & 0x40:
            run_len = (run_len << 8) | rle[i]
            i += 1
        color = 0
        if second & 0x80:
            color = rle[i]
            i += 1
        end = min(pos + run_len, len(out))
        for p in range(pos, end):
            out[p] = color
        pos = end
    return out


def _num_composition_objects(pcs: bytes) -> int:
    """Return the object count from a PCS payload (0 => a clear set).

    Layout up to the count: width(2) height(2) framerate(1)
    composition_number(2) composition_state(1) palette_update_flag(1)
    palette_id(1) number_of_composition_objects(1).
    """
    return pcs[10] if len(pcs) > 10 else 0


@dataclass
class _DisplaySet:
    pts: int
    has_composition: bool = False
    palette: dict[int, tuple[int, int, int, int]] = field(default_factory=dict)
    objects: dict[int, _ObjectDef] = field(default_factory=dict)


def _render(display_set: _DisplaySet) -> Image.Image:
    """Render a display set's first object to an RGBA image.

    Builds a flat RGBA byte buffer and hands it to ``Image.frombytes``
    rather than per-pixel ``load()`` assignment — faster and avoids the
    Optional ``PixelAccess`` load returns.
    """
    obj = next(iter(display_set.objects.values()))
    indices = _decode_rle(obj.rle, obj.width, obj.height)
    palette = display_set.palette
    transparent = (0, 0, 0, 0)
    raw = bytearray(len(indices) * 4)
    for i, idx in enumerate(indices):
        raw[i * 4 : i * 4 + 4] = bytes(palette.get(idx, transparent))
    return Image.frombytes("RGBA", (obj.width, obj.height), bytes(raw))


def parse_pgs(raw: bytes) -> list[PgsCue]:
    """Parse a PGS/SUP byte stream into timed subtitle bitmaps.

    Walks the display sets, pairing each "show" set (a composition that
    carries objects) with the next "clear" set (an empty composition) to
    recover ``start_ms``/``end_ms``. Sets without objects, palette, or a
    matching clear are skipped, so every returned cue has a renderable
    image and a positive duration.

    Args:
        raw: The raw PGS elementary stream (e.g. the bytes of a ``.sup``
            file, or a demuxed PGS subtitle stream).

    Returns:
        Cues in stream order. Empty if the stream carries no subtitles.

    Raises:
        ValueError: If ``raw`` is not a valid PGS stream (bad magic).
    """
    cues: list[PgsCue] = []
    current = _DisplaySet(pts=0)
    pending_obj: _ObjectDef | None = None
    open_start: int | None = None
    open_image: Image.Image | None = None

    for seg in _iter_segments(raw):
        if seg.type == _SEG_PCS:
            current = _DisplaySet(
                pts=seg.pts,
                has_composition=_num_composition_objects(seg.data) > 0,
            )
        elif seg.type == _SEG_PDS:
            current.palette.update(_parse_palette(seg.data))
        elif seg.type == _SEG_ODS:
            pending_obj = _accumulate_object(seg.data, pending_obj, current)
        elif seg.type == _SEG_END:
            pts_ms = current.pts // (_PTS_HZ // 1000)
            if current.has_composition and current.objects and current.palette:
                open_start = pts_ms
                open_image = _render(current)
            elif not current.has_composition:
                if open_start is not None and open_image is not None and pts_ms > open_start:
                    cues.append(PgsCue(open_start, pts_ms, open_image))
                open_start, open_image = None, None
    return cues


def _accumulate_object(
    data: bytes,
    pending: _ObjectDef | None,
    display_set: _DisplaySet,
) -> _ObjectDef | None:
    """Fold one ODS segment into the object being assembled.

    A large object spans several ODS segments: the first carries the
    dimensions + a leading RLE chunk, continuations carry more RLE, and
    the one flagged "last" is committed to the display set.
    """
    seq_flag = data[3]
    if seq_flag & _ODS_FIRST:
        obj_id = struct.unpack(">H", data[0:2])[0]
        # object_data_length(3) width(2) height(2) then RLE.
        width = struct.unpack(">H", data[7:9])[0]
        height = struct.unpack(">H", data[9:11])[0]
        pending = _ObjectDef(obj_id, width, height, data[11:])
    elif pending is not None:
        pending.rle += data[4:]
    if seq_flag & _ODS_LAST and pending is not None:
        display_set.objects[pending.obj_id] = pending
        return None
    return pending


__all__ = ["PgsCue", "parse_pgs"]
