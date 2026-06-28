"""Tests for the library request-schema → domain VO conversion."""

import pytest

from src.modules.library.domain.value_objects.metadata_provider import MetadataProvider
from src.modules.library.domain.value_objects.subtitle_mode import SubtitleMode
from src.modules.library.presentation.schemas.library_schemas import (
    LibrarySettingsSchema,
    MetadataProviderSchema,
)


@pytest.mark.unit
class TestMetadataProviderSchemaToConfig:
    """``MetadataProviderSchema.to_config`` builds the domain VO."""

    def test_maps_all_fields(self) -> None:
        config = MetadataProviderSchema(provider="omdb", priority=3, enabled=False).to_config()

        assert config.provider is MetadataProvider.OMDB
        assert config.priority == 3
        assert config.enabled is False

    def test_applies_schema_defaults(self) -> None:
        config = MetadataProviderSchema(provider="tmdb").to_config()

        assert config.provider is MetadataProvider.TMDB
        assert config.priority == 1
        assert config.enabled is True


@pytest.mark.unit
class TestLibrarySettingsSchemaToSettings:
    """``LibrarySettingsSchema.to_settings`` builds the domain VO."""

    def test_maps_all_fields(self) -> None:
        settings = LibrarySettingsSchema(
            preferred_audio_language="ja",
            preferred_subtitle_language="en",
            subtitle_mode="always",
            generate_thumbnails=False,
            detect_intros=True,
            auto_refresh_metadata=True,
        ).to_settings()

        assert settings.preferred_audio_language.value == "ja"
        assert settings.preferred_subtitle_language is not None
        assert settings.preferred_subtitle_language.value == "en"
        assert settings.subtitle_mode is SubtitleMode.ALWAYS
        assert settings.generate_thumbnails is False
        assert settings.detect_intros is True
        assert settings.auto_refresh_metadata is True

    def test_absent_subtitle_language_maps_to_none(self) -> None:
        settings = LibrarySettingsSchema(preferred_subtitle_language=None).to_settings()

        assert settings.preferred_subtitle_language is None

    def test_defaults_match_domain_defaults(self) -> None:
        # The schema defaults must round-trip to the VO's own defaults so the
        # HTTP path is equivalent to constructing the default settings.
        settings = LibrarySettingsSchema().to_settings()

        assert settings.preferred_audio_language.value == "en"
        assert settings.preferred_subtitle_language is None
        assert settings.subtitle_mode is SubtitleMode.FOREIGN_AUDIO_ONLY
        assert settings.generate_thumbnails is True
        assert settings.detect_intros is False
        assert settings.auto_refresh_metadata is False
