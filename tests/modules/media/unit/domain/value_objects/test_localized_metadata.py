"""Tests for the LocalizedMetadata value object (ADR-023)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects.localized_metadata import (
    LocalizedField,
    LocalizedFields,
    LocalizedMetadata,
)


@pytest.mark.unit
class TestLocalizedFields:
    """Per-locale record emptiness."""

    def test_is_empty_when_all_fields_unset(self) -> None:
        assert LocalizedFields().is_empty() is True

    def test_not_empty_with_any_field(self) -> None:
        assert LocalizedFields(title="X").is_empty() is False
        assert LocalizedFields(genres=("Ação",)).is_empty() is False


@pytest.mark.unit
class TestLocalizedMetadataMerge:
    """merge() overlays another VO's locales at the locale level."""

    def test_merge_overlays_provider_locale_over_existing(self) -> None:
        existing = LocalizedMetadata.from_serializable(
            {"pt-BR": {"title": "Antigo", "synopsis": "Velha sinopse"}}
        )
        provider = LocalizedMetadata.from_serializable({"pt-BR": {"title": "Novo"}})

        merged = existing.merge(provider)

        # Locale-level (not field-level) override: the whole pt-BR entry is
        # replaced, so the stale synopsis is dropped — matching the legacy
        # {**existing, **provider} behavior.
        assert merged.text(LocalizedField.TITLE, "pt-BR") == "Novo"
        assert merged.text(LocalizedField.SYNOPSIS, "pt-BR") is None

    def test_merge_keeps_locales_absent_from_provider(self) -> None:
        existing = LocalizedMetadata.from_serializable({"es": {"title": "Español"}})
        provider = LocalizedMetadata.from_serializable({"pt-BR": {"title": "Português"}})

        merged = existing.merge(provider)

        assert merged.text(LocalizedField.TITLE, "es") == "Español"
        assert merged.text(LocalizedField.TITLE, "pt-BR") == "Português"

    def test_merge_with_empty_provider_is_noop(self) -> None:
        existing = LocalizedMetadata.from_serializable({"pt-BR": {"title": "Mantido"}})

        merged = existing.merge(LocalizedMetadata())

        assert merged.to_serializable() == {"pt-BR": {"title": "Mantido"}}

    def test_merge_does_not_mutate_operands(self) -> None:
        existing = LocalizedMetadata.from_serializable({"pt-BR": {"title": "A"}})
        provider = LocalizedMetadata.from_serializable({"pt-BR": {"title": "B"}})

        existing.merge(provider)

        assert existing.text(LocalizedField.TITLE, "pt-BR") == "A"
        assert provider.text(LocalizedField.TITLE, "pt-BR") == "B"


@pytest.mark.unit
class TestLocalizedMetadataRoundTrip:
    """Serialization anchors the no-migration guarantee."""

    def test_to_serializable_omits_falsy_and_lists_genres(self) -> None:
        meta = LocalizedMetadata.from_serializable(
            {"pt-BR": {"title": "T", "synopsis": "", "genres": ["Ação"]}}
        )

        # Empty synopsis dropped; genres stays a list.
        assert meta.to_serializable() == {"pt-BR": {"title": "T", "genres": ["Ação"]}}

    def test_unknown_internal_key_is_rejected(self) -> None:
        with pytest.raises(DomainValidationException):
            LocalizedMetadata.from_serializable({"pt-BR": {"bogus": "x"}})

    def test_lenient_lookup_canonicalizes_locale(self) -> None:
        meta = LocalizedMetadata.from_serializable({"pt-BR": {"title": "Olá"}})

        # Non-canonical casing resolves; an unparseable tag just misses.
        assert meta.text(LocalizedField.TITLE, "PT-br") == "Olá"
        assert meta.text(LocalizedField.TITLE, "zz") is None
