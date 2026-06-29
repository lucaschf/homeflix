"""Tests for GetFileTracksUseCase."""

from unittest.mock import MagicMock

import pytest

from src.modules.media.application.ports import ProbeResult
from src.modules.media.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.media.application.use_cases.get_file_tracks import (
    GetFileTracksInput,
    GetFileTracksUseCase,
)
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


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
        use_case = GetFileTracksUseCase(hls=hls)

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
        use_case = GetFileTracksUseCase(hls=hls)

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
        use_case = GetFileTracksUseCase(hls=hls)

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
        use_case = GetFileTracksUseCase(hls=hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        assert output.subtitle_tracks[0]["is_default"] is True

    @pytest.mark.asyncio
    async def test_should_drop_image_based_subtitles(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        hls.probe_tracks.return_value = ProbeResult(
            audio_tracks=[_audio()],
            subtitle_tracks=[_text_subtitle(0, "en"), _image_subtitle(1, "ja")],
        )
        use_case = GetFileTracksUseCase(hls=hls)

        output = await use_case.execute(GetFileTracksInput(file_path="/m.mkv"))

        assert len(output.subtitle_tracks) == 1
        assert output.subtitle_tracks[0]["language"] == "en"
