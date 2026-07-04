"""Tests for the SubtitleOcrConfig VO (ADR-027 bucket)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import SubtitleOcrConfig


@pytest.mark.unit
class TestSubtitleOcrConfig:
    def test_defaults_are_conservative(self) -> None:
        cfg = SubtitleOcrConfig()

        assert cfg.enabled is False
        assert cfg.batch_size == 2
        assert cfg.interval_minutes == 60
        assert cfg.subdir == ".homeflix/subtitles"
        assert cfg.languages == ()
        assert cfg.tesseract_binary == "tesseract"
        assert cfg.per_cue_timeout_seconds == 30

    def test_with_updates_returns_a_modified_copy(self) -> None:
        cfg = SubtitleOcrConfig()

        updated = cfg.with_updates(enabled=True, languages=("en", "pt"))

        assert updated.enabled is True
        assert updated.languages == ("en", "pt")
        assert cfg.enabled is False  # original untouched

    def test_languages_is_hashable_so_the_vo_is_hashable(self) -> None:
        # languages must be a tuple, not a list, or the VO can't be hashed
        # like every other CompoundValueObject.
        cfg = SubtitleOcrConfig(languages=("en",))

        assert hash(cfg) == hash(SubtitleOcrConfig(languages=("en",)))

    @pytest.mark.parametrize("bad", [0, -1])
    def test_batch_size_must_be_positive(self, bad: int) -> None:
        with pytest.raises(DomainValidationException):
            SubtitleOcrConfig(batch_size=bad)

    def test_interval_must_be_positive(self) -> None:
        with pytest.raises(DomainValidationException):
            SubtitleOcrConfig(interval_minutes=0)

    def test_per_cue_timeout_must_be_positive(self) -> None:
        with pytest.raises(DomainValidationException):
            SubtitleOcrConfig(per_cue_timeout_seconds=0)
