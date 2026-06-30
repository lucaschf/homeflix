"""Tests for GetFileTracksUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.ports import ProbeResult
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.ports.profile_playback_preference_port import (
    PlaybackPreference,
    ProfilePlaybackPreferencePort,
)
from src.modules.media.application.use_cases.get_file_tracks import (
    GetFileTracksInput,
    GetFileTracksUseCase,
)
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _make_use_case(
    hls: MagicMock, preferred_audio: LanguageCode | None = None
) -> tuple[GetFileTracksUseCase, MagicMock]:
    """Build the use case with a mocked playback-preference port.

    The port returns a ``PlaybackPreference`` with the given audio language
    (default: none → no preference applied).
    """
    pref_port = MagicMock(spec=ProfilePlaybackPreferencePort)
    pref_port.for_profile = AsyncMock(
        return_value=PlaybackPreference(audio_language=preferred_audio)
    )
    return GetFileTracksUseCase(hls=hls, playback_preference=pref_port), pref_port


def _audio(index: int = 0, lang: str = "en") -> AudioTrack:
    return AudioTrack(
        index=index,
        language=LanguageCode(lang),
        codec="aac",
        channels=2,
        is_default=index == 0,
    )


def _text_subtitle(index: int = 0, lang: str = "en") -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(lang),
        format="srt",
        is_external=False,
    )


def _image_subtitle(index: int = 1, lang: str = "en") -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(lang),
        format="pgs",
        is_external=False,
    )


@pytest.mark.unit
class TestGetFileTracksUseCase:
    @pytest.mark.asyncio
    async def test_should_serialize_audio_and_text_subtitles(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[_audio(0, "en"), _audio(1, "pt")],
            subtitle_tracks=[_text_subtitle(0, "en")],
        )
        use_case, _ = _make_use_case(hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        assert len(output.audio_tracks) == 2
        assert {t["language"] for t in output.audio_tracks} == {"en", "pt"}
        assert len(output.subtitle_tracks) == 1
        assert output.subtitle_tracks[0]["format"] == "srt"
        hls.probe_tracks.assert_called_once_with("/m.mkv")

    @pytest.mark.asyncio
    async def test_marks_first_audio_default_when_container_declares_none(self) -> None:
        # Probe now reports truthfully (no fabricated default); the selector
        # must still hand the player exactly one default audio (the first).
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
                AudioTrack(index=1, language=LanguageCode("pt"), codec="ac3", channels=6),
            ],
            subtitle_tracks=[],
        )
        use_case, _ = _make_use_case(hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        defaults = [t for t in output.audio_tracks if t["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["index"] == 0

    @pytest.mark.asyncio
    async def test_preserves_container_declared_default_audio(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
                AudioTrack(
                    index=1,
                    language=LanguageCode("pt"),
                    codec="ac3",
                    channels=6,
                    is_default=True,
                ),
            ],
            subtitle_tracks=[],
        )
        use_case, _ = _make_use_case(hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        defaults = [t for t in output.audio_tracks if t["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["index"] == 1

    @pytest.mark.asyncio
    async def test_preserves_container_declared_default_subtitle(self) -> None:
        # The change is audio-only: a container-declared subtitle default
        # passes through serialize_tracks untouched.
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[_audio()],
            subtitle_tracks=[
                SubtitleTrack(
                    index=0,
                    language=LanguageCode("en"),
                    format="srt",
                    is_default=True,
                    is_external=False,
                ),
            ],
        )
        use_case, _ = _make_use_case(hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        assert output.subtitle_tracks[0]["is_default"] is True

    @pytest.mark.asyncio
    async def test_should_drop_image_based_subtitles(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[_audio()],
            subtitle_tracks=[_text_subtitle(0, "en"), _image_subtitle(1, "ja")],
        )
        use_case, _ = _make_use_case(hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        assert len(output.subtitle_tracks) == 1
        assert output.subtitle_tracks[0]["language"] == "en"

    @pytest.mark.asyncio
    async def test_profile_preferred_language_drives_default_audio(self) -> None:
        # Only the preference can explain the result: the pt track has FEWER
        # channels than en and is not the container default, so neither the
        # max-channels tiebreak nor the first/container fallback would pick it.
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="ac3", channels=6),
                AudioTrack(index=1, language=LanguageCode("pt"), codec="aac", channels=2),
            ],
            subtitle_tracks=[],
        )
        use_case, pref_port = _make_use_case(hls, preferred_audio=LanguageCode("pt"))

        output = await use_case.execute(
            GetFileTracksInput(file_path="/m.mkv", profile_id="prf_abc12345")
        )

        defaults = [t for t in output.audio_tracks if t["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["language"] == "pt"
        pref_port.for_profile.assert_awaited_once_with("prf_abc12345")

    @pytest.mark.asyncio
    async def test_profile_with_no_usable_audio_pref_falls_back_to_container(self) -> None:
        # profile_id present but the preference yields no audio language
        # (e.g. an unbridgeable tag) → the container default stands, and the
        # port was still consulted.
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
                AudioTrack(
                    index=1,
                    language=LanguageCode("pt"),
                    codec="ac3",
                    channels=6,
                    is_default=True,
                ),
            ],
            subtitle_tracks=[],
        )
        use_case, pref_port = _make_use_case(hls, preferred_audio=None)

        output = await use_case.execute(
            GetFileTracksInput(file_path="/m.mkv", profile_id="prf_abc12345")
        )

        defaults = [t for t in output.audio_tracks if t["is_default"]]
        assert defaults[0]["index"] == 1  # container default
        pref_port.for_profile.assert_awaited_once_with("prf_abc12345")

    @pytest.mark.asyncio
    async def test_no_profile_id_skips_preference_lookup(self) -> None:
        # Without a profile_id the cross-BC port is not consulted and the
        # container-declared default stands.
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
                AudioTrack(
                    index=1,
                    language=LanguageCode("pt"),
                    codec="ac3",
                    channels=6,
                    is_default=True,
                ),
            ],
            subtitle_tracks=[],
        )
        use_case, pref_port = _make_use_case(hls, preferred_audio=LanguageCode("en"))

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        defaults = [t for t in output.audio_tracks if t["is_default"]]
        assert defaults[0]["index"] == 1  # container default; preference not applied
        pref_port.for_profile.assert_not_awaited()
