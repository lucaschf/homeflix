"""Tests for the MergePolicy value object."""

import pytest

from src.modules.media.domain.value_objects.merge_policy import MergePolicy


@pytest.mark.unit
class TestMergePolicy:
    """The policy centralizes the fill-if-empty vs overwrite rule."""

    def test_fill_if_empty_writes_only_when_current_is_empty(self) -> None:
        policy = MergePolicy.FILL_IF_EMPTY
        assert policy.should_write(None) is True
        assert policy.should_write("") is True
        assert policy.should_write([]) is True
        assert policy.should_write("existing") is False
        assert policy.should_write(["x"]) is False

    def test_overwrite_always_writes(self) -> None:
        policy = MergePolicy.OVERWRITE
        assert policy.should_write(None) is True
        assert policy.should_write("existing") is True
        assert policy.should_write(["x"]) is True

    def test_from_force_maps_the_public_flag(self) -> None:
        assert MergePolicy.from_force(force=True) is MergePolicy.OVERWRITE
        assert MergePolicy.from_force(force=False) is MergePolicy.FILL_IF_EMPTY

    def test_overwrites_is_true_only_for_overwrite(self) -> None:
        assert MergePolicy.OVERWRITE.overwrites is True
        assert MergePolicy.FILL_IF_EMPTY.overwrites is False
