"""Tests for the shared provider-metadata reconciliation helpers."""

from types import SimpleNamespace

import pytest

from src.modules.media.application.use_cases._metadata_field_merge import (
    COMMON_FILL_IF_EMPTY,
    reconcile_common_fields,
    set_cast_if_missing,
    set_if_missing,
    set_provider_ids,
)
from src.modules.media.domain.value_objects import (
    ImdbId,
    LocalizedMetadata,
    MergePolicy,
    Title,
    TmdbId,
)

_FIELD_MAP = {"poster_url": ("poster_path", str.upper)}


@pytest.mark.unit
class TestSetIfMissing:
    def test_fills_an_empty_field_and_applies_the_converter(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(poster_url="abc")
        entity = SimpleNamespace(poster_path=None)

        set_if_missing(updates, metadata, entity, _FIELD_MAP)

        assert updates == {"poster_path": "ABC"}

    def test_fill_if_empty_skips_when_entity_already_has_a_value(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(poster_url="abc")
        entity = SimpleNamespace(poster_path="kept")

        set_if_missing(updates, metadata, entity, _FIELD_MAP)

        assert updates == {}

    def test_overwrite_writes_even_when_entity_has_a_value(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(poster_url="abc")
        entity = SimpleNamespace(poster_path="stale")

        set_if_missing(updates, metadata, entity, _FIELD_MAP, policy=MergePolicy.OVERWRITE)

        assert updates == {"poster_path": "ABC"}

    def test_skips_when_provider_value_is_falsy(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(poster_url=None)
        entity = SimpleNamespace(poster_path=None)

        set_if_missing(updates, metadata, entity, _FIELD_MAP)

        assert updates == {}

    def test_none_converter_passes_the_value_through(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(synopsis="plot")
        entity = SimpleNamespace(synopsis=None)

        set_if_missing(updates, metadata, entity, {"synopsis": ("synopsis", None)})

        assert updates == {"synopsis": "plot"}


@pytest.mark.unit
class TestSetProviderIds:
    def test_writes_all_three_identity_fields_as_value_objects(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(tmdb_id=27205, imdb_id="tt1375666", original_title="Inception")

        set_provider_ids(updates, metadata)

        assert updates == {
            "tmdb_id": TmdbId(27205),
            "imdb_id": ImdbId("tt1375666"),
            "original_title": Title("Inception"),
        }

    def test_skips_fields_the_provider_omits(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(tmdb_id=27205, imdb_id=None, original_title=None)

        set_provider_ids(updates, metadata)

        assert updates == {"tmdb_id": TmdbId(27205)}


@pytest.mark.unit
class TestSetCastIfMissing:
    @staticmethod
    def _person() -> SimpleNamespace:
        return SimpleNamespace(
            name="Leonardo DiCaprio", profile_url=None, role="Cobb", tmdb_id=6193
        )

    def test_fills_and_converts_credit_person_to_cast_member(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(cast=[self._person()])
        entity = SimpleNamespace(cast=[])

        set_cast_if_missing(updates, metadata, entity)

        cast = updates["cast"]
        assert [m.name for m in cast] == ["Leonardo DiCaprio"]
        assert cast[0].tmdb_id == 6193

    def test_fill_if_empty_keeps_existing_cast(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(cast=[self._person()])
        entity = SimpleNamespace(cast=["already here"])

        set_cast_if_missing(updates, metadata, entity)

        assert updates == {}

    def test_overwrite_replaces_existing_cast(self) -> None:
        updates: dict[str, object] = {}
        metadata = SimpleNamespace(cast=[self._person()])
        entity = SimpleNamespace(cast=["stale"])

        set_cast_if_missing(updates, metadata, entity, policy=MergePolicy.OVERWRITE)

        assert [m.name for m in updates["cast"]] == ["Leonardo DiCaprio"]


@pytest.mark.unit
class TestReconcileCommonFields:
    @staticmethod
    def _metadata(**overrides: object) -> SimpleNamespace:
        base = {
            "tmdb_id": 27205,
            "imdb_id": "tt1375666",
            "original_title": "Inception",
            "synopsis": "plot",
            "genres": [],
            "poster_url": None,
            "backdrop_url": None,
            "logo_url": None,
            "content_rating": None,
            "trailer_url": None,
            "cast": [SimpleNamespace(name="Leo", profile_url=None, role="Cobb", tmdb_id=6193)],
            "localized": {},
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_folds_ids_fill_and_cast_into_one_updates_dict(self) -> None:
        entity = SimpleNamespace(cast=[], localized=LocalizedMetadata({}))

        updates = reconcile_common_fields(
            entity,
            self._metadata(),
            policy=MergePolicy.FILL_IF_EMPTY,
            fill_if_empty=COMMON_FILL_IF_EMPTY,
        )

        assert updates["tmdb_id"] == TmdbId(27205)
        assert updates["synopsis"] == "plot"
        assert [m.name for m in updates["cast"]] == ["Leo"]
        # The provider supplied no localized overrides, so localized is untouched.
        assert "localized" not in updates

    def test_empty_provider_localized_leaves_localized_untouched(self) -> None:
        entity = SimpleNamespace(cast=[], localized=LocalizedMetadata({}))

        updates = reconcile_common_fields(
            entity,
            self._metadata(synopsis=None, cast=[]),
            policy=MergePolicy.FILL_IF_EMPTY,
            fill_if_empty=COMMON_FILL_IF_EMPTY,
        )

        # Only the always-overwrite provider ids remain.
        assert set(updates) == {"tmdb_id", "imdb_id", "original_title"}

    def test_overwrite_folds_over_a_populated_entity(self) -> None:
        # Under OVERWRITE the fill-if-empty guard is bypassed: provider
        # values win even when the entity already has them.
        entity = SimpleNamespace(
            synopsis="old plot", cast=["stale"], localized=LocalizedMetadata({})
        )

        updates = reconcile_common_fields(
            entity,
            self._metadata(),
            policy=MergePolicy.OVERWRITE,
            fill_if_empty=COMMON_FILL_IF_EMPTY,
        )

        assert updates["synopsis"] == "plot"
        assert [m.name for m in updates["cast"]] == ["Leo"]
