"""Tests for LibrarySettings value object."""

from src.modules.library.domain.value_objects.library_settings import LibrarySettings


class TestLibrarySettingsCreation:
    """Tests for LibrarySettings instantiation."""

    def test_should_create_with_defaults(self):
        settings = LibrarySettings()

        assert settings.generate_thumbnails is True
        assert settings.detect_intros is False
        assert settings.auto_refresh_metadata is False

    def test_should_create_with_custom_values(self):
        settings = LibrarySettings(
            generate_thumbnails=False,
            detect_intros=True,
            auto_refresh_metadata=True,
        )

        assert settings.generate_thumbnails is False
        assert settings.detect_intros is True
        assert settings.auto_refresh_metadata is True


class TestLibrarySettingsFactories:
    """Tests for LibrarySettings factory methods."""

    def test_default_should_return_scan_defaults(self):
        settings = LibrarySettings.default()

        assert settings.generate_thumbnails is True
        assert settings.detect_intros is False
        assert settings.auto_refresh_metadata is False
