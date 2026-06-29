"""Tests for the shared set_if_missing metadata merge helper."""

from types import SimpleNamespace

import pytest

from src.modules.media.application.use_cases._metadata_field_merge import set_if_missing
from src.modules.media.domain.value_objects import MergePolicy

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
