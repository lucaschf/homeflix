"""Tests for the pure PGS subtitle parser.

Builds synthetic PGS byte streams segment-by-segment so decode + timing
are validated without a binary fixture.
"""

import struct

import pytest

from src.modules.streaming.infrastructure.streaming.pgs_parser import (
    _decode_rle,
    parse_pgs,
)

_SEG_PDS = 0x14
_SEG_ODS = 0x15
_SEG_PCS = 0x16
_SEG_END = 0x80


def _segment(pts_90khz: int, seg_type: int, payload: bytes) -> bytes:
    """Assemble one PGS segment with its 13-byte header."""
    return (
        b"PG"
        + struct.pack(">I", pts_90khz)
        + struct.pack(">I", 0)  # dts (unused)
        + bytes([seg_type])
        + struct.pack(">H", len(payload))
        + payload
    )


def _pcs(num_objects: int) -> bytes:
    """A Presentation Composition Segment declaring ``num_objects``."""
    # width(2) height(2) framerate(1) compnum(2) compstate(1) palupd(1)
    # palid(1) num_objects(1) [+ per-object entries the parser ignores].
    return struct.pack(">HHBHBBBB", 2, 1, 0x10, 0, 0x80, 0, 0, num_objects)


def _pds() -> bytes:
    """A palette mapping index 1 -> opaque white (Y=235, Cr=Cb=128)."""
    return bytes([0, 0]) + bytes([1, 235, 128, 128, 255])


def _ods_2x1() -> bytes:
    """One 2x1 object, both pixels palette index 1."""
    rle = bytes([0x01, 0x01, 0x00, 0x00])  # px1, px2, end-of-line
    obj_data_len = 2 + 2 + len(rle)  # width + height + rle
    return (
        struct.pack(">H", 0)  # object id
        + bytes([0])  # version
        + bytes([0xC0])  # first + last in sequence
        + struct.pack(">I", obj_data_len)[1:]  # 3-byte data length
        + struct.pack(">H", 2)  # width
        + struct.pack(">H", 1)  # height
        + rle
    )


def _show_then_clear(show_pts: int, clear_pts: int) -> bytes:
    """A full show display set followed by a clear one."""
    return (
        _segment(show_pts, _SEG_PCS, _pcs(num_objects=1))
        + _segment(show_pts, _SEG_PDS, _pds())
        + _segment(show_pts, _SEG_ODS, _ods_2x1())
        + _segment(show_pts, _SEG_END, b"")
        + _segment(clear_pts, _SEG_PCS, _pcs(num_objects=0))
        + _segment(clear_pts, _SEG_END, b"")
    )


@pytest.mark.unit
class TestParsePgs:
    def test_pairs_show_and_clear_into_one_timed_cue(self) -> None:
        stream = _show_then_clear(show_pts=90_000, clear_pts=180_000)

        cues = parse_pgs(stream)

        assert len(cues) == 1
        assert cues[0].start_ms == 1000  # 90_000 / 90
        assert cues[0].end_ms == 2000  # 180_000 / 90

    def test_decodes_object_bitmap_through_palette(self) -> None:
        cues = parse_pgs(_show_then_clear(90_000, 180_000))

        image = cues[0].image
        assert image.size == (2, 1)
        assert image.mode == "RGBA"
        # both pixels are palette index 1 -> opaque white
        assert image.getpixel((0, 0)) == (255, 255, 255, 255)
        assert image.getpixel((1, 0)) == (255, 255, 255, 255)

    def test_multiple_cues_preserved_in_order(self) -> None:
        stream = _show_then_clear(90_000, 180_000) + _show_then_clear(270_000, 360_000)

        cues = parse_pgs(stream)

        assert [(c.start_ms, c.end_ms) for c in cues] == [(1000, 2000), (3000, 4000)]

    def test_show_without_matching_clear_is_dropped(self) -> None:
        # A show set with no following clear yields no completed cue.
        stream = (
            _segment(90_000, _SEG_PCS, _pcs(num_objects=1))
            + _segment(90_000, _SEG_PDS, _pds())
            + _segment(90_000, _SEG_ODS, _ods_2x1())
            + _segment(90_000, _SEG_END, b"")
        )

        assert parse_pgs(stream) == []

    def test_empty_stream_yields_no_cues(self) -> None:
        assert parse_pgs(b"") == []

    def test_non_pgs_stream_raises(self) -> None:
        with pytest.raises(ValueError, match="Not a PGS stream"):
            parse_pgs(b"NOTPGSDATA___________")


@pytest.mark.unit
class TestDecodeRle:
    """Per-branch coverage of the PGS run-length decoder.

    Real PGS subtitles are dominated by runs, not literal pixels — the
    integration builder above only exercises the literal + end-of-line
    path, so these cover every run-length branch explicitly.
    """

    def test_literal_pixels(self) -> None:
        # Non-zero bytes are single pixels of that palette index.
        assert list(_decode_rle(bytes([0x01, 0x02]), width=2, height=1)) == [1, 2]

    def test_end_of_line_pads_to_row_boundary(self) -> None:
        # 0x00 0x00 after one literal pads the rest of the 3-wide row with 0.
        out = _decode_rle(bytes([0x05, 0x00, 0x00, 0x07]), width=3, height=2)
        assert list(out) == [5, 0, 0, 7, 0, 0]

    def test_short_run_background(self) -> None:
        # 0x00 <len> with neither 0x40 nor 0x80: run of `len` zeros.
        assert list(_decode_rle(bytes([0x00, 0x03]), width=3, height=1)) == [0, 0, 0]

    def test_short_run_coloured(self) -> None:
        # 0x80 set: the byte after carries the colour index. 0x83 -> len 3.
        out = _decode_rle(bytes([0x00, 0x83, 0x05]), width=3, height=1)
        assert list(out) == [5, 5, 5]

    def test_extended_length_run(self) -> None:
        # 0x40 set: length spans two bytes (low 6 bits << 8 | next). 300 zeros
        # into a 400-wide buffer.
        second = 0x40 | ((300 >> 8) & 0x3F)  # 0x41
        low = 300 & 0xFF  # 0x2C
        out = _decode_rle(bytes([0x00, second, low]), width=400, height=1)
        assert out[:300] == bytearray(300)
        assert len(out) == 400

    def test_extended_length_coloured_run(self) -> None:
        # 0x40 | 0x80: two-byte length AND a trailing colour byte. 100 px of 7.
        second = 0x40 | 0x80 | ((100 >> 8) & 0x3F)  # 0xC0
        low = 100 & 0xFF  # 0x64
        out = _decode_rle(bytes([0x00, second, low, 0x07]), width=100, height=1)
        assert list(out) == [7] * 100

    def test_run_overflowing_buffer_is_clamped(self) -> None:
        # A run longer than width*height clamps rather than overrunning.
        out = _decode_rle(bytes([0x00, 0x8A, 0x03]), width=2, height=1)  # len 10, colour 3
        assert list(out) == [3, 3]

    def test_mixed_literal_run_and_eol(self) -> None:
        out = _decode_rle(
            bytes([0x09, 0x00, 0x82, 0x04, 0x00, 0x00, 0x08]),  # px9, run(2x4), eol, px8
            width=4,
            height=2,
        )
        assert list(out) == [9, 4, 4, 0, 8, 0, 0, 0]

    def test_truncated_run_header_stops_cleanly(self) -> None:
        # A lone 0x00 with no following byte just ends the loop.
        assert list(_decode_rle(bytes([0x02, 0x00]), width=2, height=1)) == [2, 0]
