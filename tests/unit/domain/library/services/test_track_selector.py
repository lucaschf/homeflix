"""Tests for TrackSelector domain service."""

from src.domain.library.services.track_selector import TrackSelector
from src.domain.library.value_objects.language_code import LanguageCode
from src.domain.library.value_objects.subtitle_mode import SubtitleMode
from src.domain.library.value_objects.tracks import AudioTrack, SubtitleTrack


class TestTrackSelectorAudioSelection:
    """Tests for TrackSelector.select_audio()."""

    def setup_method(self):
        self.selector = TrackSelector()

    def test_should_return_none_for_empty_list(self):
        result = self.selector.select_audio([], LanguageCode("en"))

        assert result is None

    def test_should_select_preferred_language_track(self):
        tracks = [
            AudioTrack(index=0, language=LanguageCode("ja"), codec="aac", channels=2),
            AudioTrack(index=1, language=LanguageCode("en"), codec="aac", channels=2),
        ]

        result = self.selector.select_audio(tracks, LanguageCode("en"))

        assert result.language.value == "en"

    def test_should_prefer_higher_channel_count_for_same_language(self):
        tracks = [
            AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
            AudioTrack(index=1, language=LanguageCode("en"), codec="dts", channels=6),
            AudioTrack(index=2, language=LanguageCode("en"), codec="truehd", channels=8),
        ]

        result = self.selector.select_audio(tracks, LanguageCode("en"))

        assert result.channels == 8

    def test_should_fallback_to_default_track_if_no_preferred_language(self):
        tracks = [
            AudioTrack(index=0, language=LanguageCode("ja"), codec="aac", channels=2),
            AudioTrack(
                index=1,
                language=LanguageCode("fr"),
                codec="dts",
                channels=6,
                is_default=True,
            ),
        ]

        result = self.selector.select_audio(tracks, LanguageCode("en"))

        assert result.is_default is True
        assert result.language.value == "fr"

    def test_should_fallback_to_highest_channel_count_if_no_default(self):
        tracks = [
            AudioTrack(index=0, language=LanguageCode("ja"), codec="aac", channels=2),
            AudioTrack(index=1, language=LanguageCode("fr"), codec="dts", channels=6),
        ]

        result = self.selector.select_audio(tracks, LanguageCode("en"))

        assert result.channels == 6


class TestTrackSelectorSubtitleSelection:
    """Tests for TrackSelector.select_subtitle()."""

    def setup_method(self):
        self.selector = TrackSelector()

    def test_should_return_none_for_empty_list(self):
        result = self.selector.select_subtitle(
            [],
            LanguageCode("en"),
            LanguageCode("en"),
            SubtitleMode.ALWAYS,
        )

        assert result is None

    def test_should_return_none_for_none_mode(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("ja"),
            LanguageCode("en"),
            SubtitleMode.NONE,
        )

        assert result is None

    def test_should_return_subtitle_in_always_mode(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
            SubtitleTrack(index=1, language=LanguageCode("pt"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("en"),  # audio is English
            LanguageCode("en"),  # preferred subtitle is English
            SubtitleMode.ALWAYS,
        )

        assert result is not None
        assert result.language.value == "en"

    def test_should_return_subtitle_for_foreign_audio_only_when_audio_is_foreign(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("ja"),  # audio is Japanese (foreign)
            LanguageCode("en"),  # preferred subtitle is English
            SubtitleMode.FOREIGN_AUDIO_ONLY,
        )

        assert result is not None
        assert result.language.value == "en"

    def test_should_return_none_for_foreign_audio_only_when_audio_matches(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("en"),  # audio is English (matches preferred)
            LanguageCode("en"),  # preferred subtitle is English
            SubtitleMode.FOREIGN_AUDIO_ONLY,
        )

        assert result is None

    def test_should_return_forced_subtitle_in_forced_only_mode(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
            SubtitleTrack(index=1, language=LanguageCode("en"), format="pgs", is_forced=True),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("en"),
            LanguageCode("en"),
            SubtitleMode.FORCED_ONLY,
        )

        assert result is not None
        assert result.is_forced is True

    def test_should_return_none_in_forced_only_mode_when_no_forced_tracks(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("en"),
            LanguageCode("en"),
            SubtitleMode.FORCED_ONLY,
        )

        assert result is None

    def test_should_prefer_text_based_over_image_based(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("en"), format="pgs"),
            SubtitleTrack(index=1, language=LanguageCode("en"), format="srt"),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("ja"),
            LanguageCode("en"),
            SubtitleMode.ALWAYS,
        )

        assert result.format == "srt"

    def test_should_prefer_forced_in_preferred_language(self):
        tracks = [
            SubtitleTrack(index=0, language=LanguageCode("ja"), format="pgs", is_forced=True),
            SubtitleTrack(index=1, language=LanguageCode("en"), format="pgs", is_forced=True),
        ]

        result = self.selector.select_subtitle(
            tracks,
            LanguageCode("en"),
            LanguageCode("en"),
            SubtitleMode.FORCED_ONLY,
        )

        assert result.language.value == "en"
