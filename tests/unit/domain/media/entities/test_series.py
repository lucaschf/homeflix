"""Tests for Series aggregate root."""

import pytest

from src.domain.shared.exceptions.domain import (
    BusinessRuleViolationException,
    DomainValidationException,
)


class TestSeriesCreation:
    """Tests for Series instantiation."""

    def test_should_create_with_required_fields(self):
        from src.domain.media.entities import Series
        from src.domain.media.value_objects import Title, Year

        series = Series(
            title=Title("Breaking Bad"),
            start_year=Year(2008),
        )

        assert series.id is None
        assert series.title.value == "Breaking Bad"
        assert series.start_year.value == 2008
        assert series.end_year is None
        assert series.is_ongoing is True

    def test_should_create_via_factory_with_auto_id(self):
        from src.domain.media.entities import Series
        from src.domain.media.value_objects import SeriesId

        series = Series.create(
            title="Breaking Bad",
            start_year=2008,
        )

        assert series.id is not None
        assert isinstance(series.id, SeriesId)
        assert series.id.prefix == "ser"

    def test_should_create_with_end_year(self):
        from src.domain.media.entities import Series
        from src.domain.media.value_objects import Title, Year

        series = Series(
            title=Title("Breaking Bad"),
            start_year=Year(2008),
            end_year=Year(2013),
        )

        assert series.end_year is not None
        assert series.end_year.value == 2013
        assert series.is_ongoing is False

    def test_should_raise_error_when_end_year_before_start_year(self):
        from src.domain.media.entities import Series
        from src.domain.media.value_objects import Title, Year

        with pytest.raises(DomainValidationException, match="end_year"):
            Series(
                title=Title("Breaking Bad"),
                start_year=Year(2013),
                end_year=Year(2008),
            )


class TestSeriesSeasonManagement:
    """Tests for Series season management."""

    def test_season_count_should_return_zero_when_empty(self):
        from src.domain.media.entities import Series

        series = Series.create(title="Breaking Bad", start_year=2008)

        assert series.season_count == 0

    def test_total_episodes_should_return_zero_when_empty(self):
        from src.domain.media.entities import Series

        series = Series.create(title="Breaking Bad", start_year=2008)

        assert series.total_episodes == 0

    def test_should_add_season(self):
        from src.domain.media.entities import Season, Series
        from src.domain.media.value_objects import SeasonId

        series = Series.create(title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )

        series = series.with_season(season)

        assert series.season_count == 1

    def test_should_raise_error_when_adding_season_with_wrong_series_id(self):
        from src.domain.media.entities import Season, Series
        from src.domain.media.value_objects import SeasonId, SeriesId

        series = Series.create(title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=SeriesId.generate(),  # Different series
            season_number=1,
        )

        with pytest.raises(BusinessRuleViolationException, match="series_id"):
            series.with_season(season)

    def test_should_get_season_by_number(self):
        from src.domain.media.entities import Season, Series
        from src.domain.media.value_objects import SeasonId

        series = Series.create(title="Breaking Bad", start_year=2008)

        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=2,
        )

        series = series.with_season(season)

        found = series.get_season(2)
        assert found == season

    def test_should_return_none_when_season_not_found(self):
        from src.domain.media.entities import Series

        series = Series.create(title="Breaking Bad", start_year=2008)

        found = series.get_season(99)
        assert found is None


class TestSeriesEquality:
    """Tests for Series equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.domain.media.entities import Series
        from src.domain.media.value_objects import SeriesId, Title, Year

        series_id = SeriesId.generate()

        series1 = Series(
            id=series_id,
            title=Title("Breaking Bad"),
            start_year=Year(2008),
        )

        series2 = Series(
            id=series_id,
            title=Title("Different"),
            start_year=Year(2010),
        )

        assert series1 == series2


class TestSeriesEvents:
    """Tests for Series domain events."""

    def test_should_add_and_pull_events(self):
        from src.domain.media.entities import Series

        series = Series.create(title="Breaking Bad", start_year=2008)

        series.add_event({"type": "SeriesCreated", "series_id": str(series.id)})

        assert series.has_pending_events is True

        events = series.pull_events()

        assert len(events) == 1
        assert series.has_pending_events is False
