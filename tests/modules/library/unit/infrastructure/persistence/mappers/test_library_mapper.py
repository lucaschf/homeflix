"""Tests for LibraryMapper: scan_schedule (CronExpression) + settings round-trip."""

import json

import pytest

from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.cron_expression import CronExpression
from src.modules.library.domain.value_objects.library_settings import LibrarySettings
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.infrastructure.persistence.mappers.library_mapper import (
    LibraryMapper,
)


def _library(scan_schedule: str | None) -> Library:
    return Library.create(
        name="Movies",
        library_type=LibraryType.MOVIES,
        paths=["/media/movies"],
        scan_schedule=scan_schedule,
    )


@pytest.mark.unit
class TestLibraryMapperScanSchedule:
    """The CronExpression VO must unwrap on write and re-hydrate on read."""

    def test_to_model_serializes_cron_to_string(self) -> None:
        model = LibraryMapper.to_model(_library("30 5 * * *"))

        assert model.scan_schedule == "30 5 * * *"  # plain str in the column

    def test_none_schedule_round_trips(self) -> None:
        model = LibraryMapper.to_model(_library(None))
        assert model.scan_schedule is None

        entity = LibraryMapper.to_entity(model)
        assert entity.scan_schedule is None

    def test_to_entity_rehydrates_cron(self) -> None:
        model = LibraryMapper.to_model(_library("0 4 * * mon-fri"))

        entity = LibraryMapper.to_entity(model)

        assert entity.scan_schedule == CronExpression("0 4 * * mon-fri")

    def test_to_entity_degrades_invalid_persisted_cron_to_none(self) -> None:
        # A row persisted before the CronExpression invariant existed (or
        # hand-edited) must not blow up hydration / find_all — it degrades.
        model = LibraryMapper.to_model(_library("30 5 * * *"))
        model.scan_schedule = "99 99 * * *"  # bypasses the write-path invariant

        entity = LibraryMapper.to_entity(model)

        assert entity.scan_schedule is None


@pytest.mark.unit
class TestLibraryMapperSettings:
    """LibrarySettings (scan toggles) must round-trip, and legacy playback keys
    from pre-ADR-026 rows must be ignored on hydration (no migration)."""

    _NON_DEFAULT = LibrarySettings(
        generate_thumbnails=False,
        detect_intros=True,
        auto_refresh_metadata=True,
    )

    def test_settings_round_trip(self) -> None:
        lib = Library.create(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
            settings=self._NON_DEFAULT,
        )

        entity = LibraryMapper.to_entity(LibraryMapper.to_model(lib))

        assert entity.settings == self._NON_DEFAULT

    def test_legacy_playback_keys_are_ignored_on_hydration(self) -> None:
        # Rows persisted before ADR-026 still carry preferred_audio_language /
        # preferred_subtitle_language / subtitle_mode in the settings JSON.
        # Hydration must drop them, not crash — the migration-free path.
        model = LibraryMapper.to_model(_library(None))
        model.settings = json.dumps(
            {
                "preferred_audio_language": "ja",
                "preferred_subtitle_language": "en",
                "subtitle_mode": "always",
                "generate_thumbnails": False,
                "detect_intros": True,
                "auto_refresh_metadata": True,
            }
        )

        entity = LibraryMapper.to_entity(model)

        assert entity.settings == self._NON_DEFAULT
        assert not hasattr(entity.settings, "preferred_audio_language")
