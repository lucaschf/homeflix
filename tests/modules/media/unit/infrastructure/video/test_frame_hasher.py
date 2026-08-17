"""Tests for the perceptual-hash core of FrameHasher.

Exercise ``_hash_raw_frames`` directly on synthetic rgb24 bytes — the
consumers (correlator / intro detector) stub FrameHasher out, so the
reshape + dHash-replication that produces a hash from real pixels was
otherwise unverified.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.modules.media.infrastructure.video.frame_hasher import FrameHasher

_SCALE = 64
_CHANNELS = 3


def _hasher() -> FrameHasher:
    """A FrameHasher with a stub config port — ``_hash_raw_frames`` ignores it."""
    return FrameHasher(runtime_settings=MagicMock())


def _gradient_frame(*, reverse: bool = False) -> np.ndarray:
    """A greyscale left-to-right gradient as an rgb24 ``(_SCALE, _SCALE, 3)`` frame."""
    cols = np.linspace(0, 255, _SCALE, dtype=np.uint8)
    if reverse:
        cols = cols[::-1]
    plane = np.repeat(cols[None, :], _SCALE, axis=0)  # (_SCALE, _SCALE)
    return np.repeat(plane[:, :, None], _CHANNELS, axis=2).astype(np.uint8)


@pytest.mark.unit
class TestHashRawFrames:
    def test_identical_frames_hash_equal(self) -> None:
        hasher = _hasher()
        frame = _gradient_frame()
        raw = frame.tobytes() * 2

        hashes = hasher._hash_raw_frames(raw, "test.mkv")

        assert hashes is not None
        assert hashes.dtype == np.uint64
        assert hashes.shape == (2,)
        assert hashes[0] == hashes[1]  # same pixels -> same hash (Hamming 0)

    def test_gradient_and_its_mirror_differ(self) -> None:
        hasher = _hasher()
        raw = _gradient_frame().tobytes() + _gradient_frame(reverse=True).tobytes()

        hashes = hasher._hash_raw_frames(raw, "test.mkv")

        assert hashes is not None
        # dHash compares each pixel to its right neighbour: the increasing
        # gradient sets every bit, the decreasing mirror clears every bit.
        assert hashes[0] != hashes[1]

    def test_truncated_buffer_returns_none(self) -> None:
        hasher = _hasher()
        # One byte short of a full frame -> zero complete frames.
        raw = bytes(_SCALE * _SCALE * _CHANNELS - 1)

        assert hasher._hash_raw_frames(raw, "test.mkv") is None

    def test_hash_length_matches_frame_count(self) -> None:
        hasher = _hasher()
        raw = _gradient_frame().tobytes() * 5

        hashes = hasher._hash_raw_frames(raw, "test.mkv")

        assert hashes is not None
        assert hashes.shape == (5,)
