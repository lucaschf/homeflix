"""Tests for LibrarySettings value object."""

from src.domain.library.value_objects.language_code import LanguageCode
from src.domain.library.value_objects.library_settings import LibrarySettings
from src.domain.library.value_objects.subtitle_mode import SubtitleMode


class TestLibrarySettingsCreation:
    """Tests for LibrarySettings instantiation."""

    def test_should_create_with_defaults(self):
        settings = LibrarySettings()

        assert settings.preferred_audio_language.value == "en"
        assert settings.preferred_subtitle_language is None
        assert settings.subtitle_mode == SubtitleMode.FOREIGN_AUDIO_ONLY
        assert settings.generate_thumbnails is True
        assert settings.detect_intros is False
        assert settings.auto_refresh_metadata is False

    def test_should_create_with_custom_values(self):
        settings = LibrarySettings(
            preferred_audio_language=LanguageCode("ja"),
            preferred_subtitle_language=LanguageCode("en"),
            subtitle_mode=SubtitleMode.ALWAYS,
            generate_thumbnails=False,
            detect_intros=True,
            auto_refresh_metadata=True,
        )

        assert settings.preferred_audio_language.value == "ja"
        assert settings.preferred_subtitle_language.value == "en"
        assert settings.subtitle_mode == SubtitleMode.ALWAYS
        assert settings.generate_thumbnails is False
        assert settings.detect_intros is True
        assert settings.auto_refresh_metadata is True


class TestLibrarySettingsFactories:
    """Tests for LibrarySettings factory methods."""

    def test_default_should_return_english_settings(self):
        settings = LibrarySettings.default()

        assert settings.preferred_audio_language.value == "en"
        assert settings.preferred_subtitle_language is None
        assert settings.subtitle_mode == SubtitleMode.FOREIGN_AUDIO_ONLY

    def test_for_anime_should_return_japanese_audio_english_subtitles(self):
        settings = LibrarySettings.for_anime()

        assert settings.preferred_audio_language.value == "ja"
        assert settings.preferred_subtitle_language.value == "en"
        assert settings.subtitle_mode == SubtitleMode.ALWAYS

    def test_for_foreign_films_should_return_foreign_audio_mode(self):
        settings = LibrarySettings.for_foreign_films()

        assert settings.preferred_subtitle_language.value == "en"
        assert settings.subtitle_mode == SubtitleMode.FOREIGN_AUDIO_ONLY

    def test_for_foreign_films_should_accept_custom_subtitle_language(self):
        settings = LibrarySettings.for_foreign_films(subtitle_language="pt")

        assert settings.preferred_subtitle_language.value == "pt"
