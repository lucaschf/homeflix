"""Tests for Series aggregate root."""

import pytest

from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)

_LIBRARY_ID = "lib_test12345678"


class TestSeriesCreation:
    """Tests for Series instantiation."""

    def test_should_create_with_required_fields(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import Title, Year

        series = Series(
            library_id=_LIBRARY_ID,
            title=Title("Breaking Bad"),
            start_year=Year(2008),
        )

        assert series.id is None
        assert series.title.value == "Breaking Bad"
        assert series.start_year.value == 2008
        assert series.end_year is None
        assert series.is_ongoing is True

    def test_should_create_via_factory_with_auto_id(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import SeriesId

        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
        )

        assert series.id is not None
        assert isinstance(series.id, SeriesId)
        assert series.id.prefix == "ser"

    def test_should_create_with_end_year(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import Title, Year

        series = Series(
            library_id=_LIBRARY_ID,
            title=Title("Breaking Bad"),
            start_year=Year(2008),
            end_year=Year(2013),
        )

        assert series.end_year is not None
        assert series.end_year.value == 2013
        assert series.is_ongoing is False

    def test_should_raise_error_when_end_year_before_start_year(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import Title, Year

        with pytest.raises(DomainValidationException, match="end_year"):
            Series(
                library_id=_LIBRARY_ID,
                title=Title("Breaking Bad"),
                start_year=Year(2013),
                end_year=Year(2008),
            )


class TestSeriesSeasonManagement:
    """Tests for Series season management."""

    def test_season_count_should_return_zero_when_empty(self):
        from src.modules.media.domain.entities import Series

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        assert series.season_count == 0

    def test_total_episodes_should_return_zero_when_empty(self):
        from src.modules.media.domain.entities import Series

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        assert series.total_episodes == 0

    def test_should_add_season(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )

        series = series.with_season(season)

        assert series.season_count == 1

    def test_should_raise_error_when_adding_season_with_wrong_series_id(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=SeriesId.generate(),  # Different series
            season_number=1,
        )

        with pytest.raises(BusinessRuleViolationException, match="series_id"):
            series.with_season(season)

    def test_upsert_should_append_a_new_season(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        season = Season(id=SeasonId.generate(), series_id=series.id, season_number=1)

        series = series.with_season_upserted(season)

        assert series.season_count == 1

    def test_upsert_should_replace_existing_season_with_same_number(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        original = Season(id=SeasonId.generate(), series_id=series.id, season_number=1)
        series = series.with_season(original)

        replacement = Season(id=SeasonId.generate(), series_id=series.id, season_number=1)
        series = series.with_season_upserted(replacement)

        assert series.season_count == 1
        assert series.seasons[0].id == replacement.id
        assert series.seasons[0].id != original.id

    def test_upsert_should_reject_season_with_wrong_series_id(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        season = Season(id=SeasonId.generate(), series_id=SeriesId.generate(), season_number=1)

        with pytest.raises(BusinessRuleViolationException, match="series_id"):
            series.with_season_upserted(season)

    def test_should_get_season_by_number(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=2,
        )

        series = series.with_season(season)

        found = series.get_season(2)
        assert found == season

    def test_should_return_none_when_season_not_found(self):
        from src.modules.media.domain.entities import Series

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        found = series.get_season(99)
        assert found is None


class TestSeriesIntroMarkedCount:
    """Tests for Series.intro_marked_count."""

    @staticmethod
    def _episode(series_id, season_number, episode_number, *, with_intro):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            IntroMarker,
            IntroMarkerSource,
            MediaFile,
            Resolution,
            Title,
        )

        episode = Episode(
            series_id=series_id,
            season_number=season_number,
            episode_number=episode_number,
            title=Title(f"Ep {episode_number}"),
            duration=Duration(2700),
            files=[
                MediaFile(
                    file_path=FilePath(
                        f"/series/show/s{season_number:02d}e{episode_number:02d}.mkv"
                    ),
                    file_size=1_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )
        if with_intro:
            episode = episode.with_intro_marker(
                IntroMarker(start_seconds=10, end_seconds=80, source=IntroMarkerSource.MANUAL)
            )
        return episode

    def _series_with(self, marked_flags_by_season):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        for season_number, flags in enumerate(marked_flags_by_season, start=1):
            season = Season(
                id=SeasonId.generate(),
                series_id=series.id,
                season_number=season_number,
                episodes=[
                    self._episode(series.id, season_number, n + 1, with_intro=flag)
                    for n, flag in enumerate(flags)
                ],
            )
            series = series.with_season(season)
        return series

    def test_should_return_zero_when_no_episodes(self):
        series = self._series_with([])

        assert series.intro_marked_count == 0

    def test_should_return_zero_when_no_episode_has_intro(self):
        series = self._series_with([[False, False, False]])

        assert series.intro_marked_count == 0

    def test_should_count_only_episodes_with_intro_marker(self):
        series = self._series_with([[True, False, True]])

        assert series.intro_marked_count == 2

    def test_should_sum_marked_episodes_across_seasons(self):
        series = self._series_with([[True, False], [True, True, False]])

        assert series.intro_marked_count == 3
        assert series.total_episodes == 5


class TestSeriesQuality:
    """Tests for Series.best_resolution and Series.has_hdr."""

    @staticmethod
    def _episode(series_id, season_number, episode_number, resolution, hdr_format):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            MediaFile,
            Resolution,
            Title,
        )

        files = []
        if resolution is not None:
            files.append(
                MediaFile(
                    file_path=FilePath(
                        f"/series/show/s{season_number:02d}e{episode_number:02d}.mkv"
                    ),
                    file_size=1_000_000_000,
                    resolution=Resolution(resolution),
                    hdr_format=hdr_format,
                    is_primary=True,
                )
            )
        return Episode(
            series_id=series_id,
            season_number=season_number,
            episode_number=episode_number,
            title=Title(f"Ep {episode_number}"),
            duration=Duration(2700),
            files=files,
        )

    def _series_with(self, seasons):
        """Build a series from ``[[(resolution, hdr_format), ...], ...]``."""
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        for season_number, specs in enumerate(seasons, start=1):
            season = Season(
                id=SeasonId.generate(),
                series_id=series.id,
                season_number=season_number,
                episodes=[
                    self._episode(series.id, season_number, n + 1, resolution, hdr_format)
                    for n, (resolution, hdr_format) in enumerate(specs)
                ],
            )
            series = series.with_season(season)
        return series

    def test_best_resolution_should_be_none_without_seasons(self):
        series = self._series_with([])

        assert series.best_resolution is None

    def test_best_resolution_should_be_none_when_no_episode_has_a_file(self):
        series = self._series_with([[(None, None), (None, None)]])

        assert series.best_resolution is None

    def test_best_resolution_should_return_highest_across_seasons(self):
        series = self._series_with([[("720p", None)], [("4K", None), ("1080p", None)]])

        best = series.best_resolution
        assert best is not None
        assert best.name == "4K"

    def test_best_resolution_should_ignore_episodes_without_files(self):
        series = self._series_with([[(None, None), ("1080p", None)]])

        best = series.best_resolution
        assert best is not None
        assert best.name == "1080p"

    def test_has_hdr_should_be_false_when_no_episode_is_hdr(self):
        series = self._series_with([[("1080p", None), ("4K", None)]])

        assert series.has_hdr is False

    def test_has_hdr_should_be_true_when_any_episode_is_hdr(self):
        from src.modules.media.domain.value_objects import HdrFormat

        series = self._series_with([[("1080p", None)], [("4K", HdrFormat.HDR10)]])

        assert series.has_hdr is True


class TestSeriesEquality:
    """Tests for Series equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import SeriesId, Title, Year

        series_id = SeriesId.generate()

        series1 = Series(
            library_id=_LIBRARY_ID,
            id=series_id,
            title=Title("Breaking Bad"),
            start_year=Year(2008),
        )

        series2 = Series(
            library_id=_LIBRARY_ID,
            id=series_id,
            title=Title("Different"),
            start_year=Year(2010),
        )

        assert series1 == series2


class TestSeriesEvents:
    """Tests for Series domain events."""

    def test_should_emit_media_created_event_on_create(self):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.events import MediaCreatedEvent

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        assert series.has_pending_events is True

        events = series.pull_events()

        assert len(events) == 1
        from src.shared_kernel.value_objects.media_type import MediaType

        assert isinstance(events[0], MediaCreatedEvent)
        assert events[0].media_id == series.id
        assert events[0].media_type is MediaType.SERIES
        assert series.has_pending_events is False

    def test_should_add_and_pull_events(self):
        from src.modules.media.domain.entities import Series

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        from dataclasses import dataclass

        from src.building_blocks.domain.events import DomainEvent

        @dataclass(frozen=True)
        class _FakeEvent(DomainEvent):
            pass

        series.add_event(_FakeEvent())

        events = series.pull_events()

        # MediaCreatedEvent from create() + the custom event
        assert len(events) == 2
        assert series.has_pending_events is False


class TestSeriesImmutability:
    """Tests for Series frozen (immutable) behavior."""

    def test_should_reject_direct_attribute_assignment(self):
        from src.modules.media.domain.entities import Series

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)

        with pytest.raises(DomainValidationException):
            series.start_year = 2020  # type: ignore[assignment, misc]

    def test_with_season_should_return_new_instance(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )

        updated = series.with_season(season)

        assert updated is not series
        assert updated.season_count == 1
        assert series.season_count == 0

    def test_with_season_should_preserve_identity(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )

        updated = series.with_season(season)

        assert updated == series  # same id

    def test_with_season_duplicate_should_return_self(self):
        from src.modules.media.domain.entities import Season, Series
        from src.modules.media.domain.value_objects import SeasonId

        series = Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )
        series = series.with_season(season)

        result = series.with_season(season)

        assert result is series


class TestSeriesLogoLocalization:
    """Tests for ``Series.get_logo_path`` per-language fallback."""

    def _series(self, **kwargs):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import ImageUrl, Title, Year

        defaults: dict[str, object] = {
            "title": Title("Breaking Bad"),
            "start_year": Year(2008),
            "logo_path": ImageUrl("https://img.example/en.png"),
            "localized": {
                "pt-BR": {
                    "title": "Quimica do Mal",
                    "logo_path": "https://img.example/ptbr.png",
                },
            },
        }
        defaults.update(kwargs)
        return Series(library_id=_LIBRARY_ID, **defaults)

    def test_returns_localized_logo_when_lang_has_one(self):
        series = self._series()
        assert series.get_logo_path("pt-BR") == "https://img.example/ptbr.png"

    def test_falls_back_to_default_logo_when_lang_missing(self):
        series = self._series()
        assert series.get_logo_path("es") == "https://img.example/en.png"

    def test_falls_back_to_default_when_localized_entry_has_no_logo(self):
        series = self._series(localized={"pt-BR": {"title": "Quimica do Mal"}})
        assert series.get_logo_path("pt-BR") == "https://img.example/en.png"

    def test_returns_none_when_no_logo_anywhere(self):
        series = self._series(logo_path=None, localized={})
        assert series.get_logo_path("en") is None


class TestSeriesPosterBackdropLocalization:
    """Tests for ``Series.get_poster_path`` / ``get_backdrop_path`` fallback."""

    def _series(self, **kwargs):
        from src.modules.media.domain.entities import Series
        from src.modules.media.domain.value_objects import ImageUrl, Title, Year

        defaults: dict[str, object] = {
            "title": Title("Breaking Bad"),
            "start_year": Year(2008),
            "poster_path": ImageUrl("https://img.example/en-poster.jpg"),
            "backdrop_path": ImageUrl("https://img.example/en-backdrop.jpg"),
            "localized": {
                "pt-BR": {
                    "poster_path": "https://img.example/ptbr-poster.jpg",
                    "backdrop_path": "https://img.example/ptbr-backdrop.jpg",
                },
            },
        }
        defaults.update(kwargs)
        return Series(library_id=_LIBRARY_ID, **defaults)

    def test_returns_localized_artwork_when_lang_has_it(self):
        series = self._series()
        assert series.get_poster_path("pt-BR") == "https://img.example/ptbr-poster.jpg"
        assert series.get_backdrop_path("pt-BR") == "https://img.example/ptbr-backdrop.jpg"

    def test_falls_back_to_english_when_lang_missing(self):
        series = self._series()
        assert series.get_poster_path("es") == "https://img.example/en-poster.jpg"
        assert series.get_backdrop_path("es") == "https://img.example/en-backdrop.jpg"

    def test_falls_back_to_english_when_localized_entry_lacks_artwork(self):
        series = self._series(localized={"pt-BR": {"title": "Quimica do Mal"}})
        assert series.get_poster_path("pt-BR") == "https://img.example/en-poster.jpg"
        assert series.get_backdrop_path("pt-BR") == "https://img.example/en-backdrop.jpg"

    def test_returns_none_when_no_artwork_anywhere(self):
        series = self._series(poster_path=None, backdrop_path=None, localized={})
        assert series.get_poster_path("en") is None
        assert series.get_backdrop_path("en") is None


class TestSeriesEnrichmentReview:
    """Tests for the enrichment-review flag transition."""

    @staticmethod
    def _series():
        from src.modules.media.domain.entities import Series

        return Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
        )

    def test_should_flag_for_review(self):
        series = self._series()
        assert series.needs_enrichment_review is False

        flagged = series.with_enrichment_review_flagged()

        assert flagged.needs_enrichment_review is True
        # Immutability: the original is untouched.
        assert series.needs_enrichment_review is False

    def test_should_be_idempotent_when_already_flagged(self):
        series = self._series().with_enrichment_review_flagged()

        again = series.with_enrichment_review_flagged()

        # Same instance — no spurious updated_at bump on re-flag.
        assert again is series
