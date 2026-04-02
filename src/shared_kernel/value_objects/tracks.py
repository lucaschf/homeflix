"""Audio and subtitle track value objects."""

from typing import ClassVar

from pydantic import Field, model_validator

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode

# Channel count to human-readable layout mapping
CHANNEL_LAYOUTS: dict[int, str] = {
    1: "Mono",
    2: "Stereo",
    6: "5.1",
    8: "7.1",
}


class AudioTrack(CompoundValueObject):
    """An audio track within a media file.

    Represents a single audio stream in a video container (MKV, MP4, etc.)
    with its technical characteristics.

    Attributes:
        index: Track index in the container (0-based).
        language: ISO 639-1 language code.
        codec: Audio codec (aac, ac3, dts, dts-hd, truehd, etc.).
        channels: Number of audio channels (2=stereo, 6=5.1, 8=7.1).
        title: Descriptive title from file metadata.
        is_default: Whether marked as default in the container.
        bitrate: Bitrate in kbps, if available.

    Example:
        >>> track = AudioTrack(
        ...     index=0,
        ...     language=LanguageCode("en"),
        ...     codec="dts-hd",
        ...     channels=8,
        ...     title="English DTS-HD MA 7.1",
        ...     is_default=True,
        ... )
        >>> track.is_surround
        True
    """

    index: int = Field(ge=0)
    language: LanguageCode
    codec: str
    channels: int = Field(ge=1, le=16)
    title: str | None = None
    is_default: bool = False
    bitrate: int | None = Field(default=None, ge=0)

    @property
    def is_stereo(self) -> bool:
        """Check if track is stereo (2 channels)."""
        return self.channels == 2

    @property
    def is_surround(self) -> bool:
        """Check if track is surround sound (more than 2 channels)."""
        return self.channels > 2

    @property
    def channel_layout(self) -> str:
        """Get human-readable channel layout.

        Returns:
            Channel layout string (e.g., "5.1", "7.1", "Stereo").
        """
        return CHANNEL_LAYOUTS.get(self.channels, f"{self.channels}ch")


class SubtitleTrack(CompoundValueObject):
    """A subtitle track for a media file.

    Can be embedded in the container or an external file.

    Attributes:
        index: Track index (0-based, unique across embedded + external).
        language: ISO 639-1 language code.
        format: Subtitle format (srt, ass, vtt, pgs, sup).
        title: Descriptive title.
        is_default: Whether marked as default.
        is_forced: Whether this is a forced subtitle track (signs only).
        is_external: True if from separate file, False if embedded.
        file_path: Path to external subtitle file, if applicable.

    Example:
        >>> embedded = SubtitleTrack(
        ...     index=0,
        ...     language=LanguageCode("en"),
        ...     format="pgs",
        ...     is_default=True,
        ...     is_external=False,
        ... )
        >>> external = SubtitleTrack(
        ...     index=2,
        ...     language=LanguageCode("pt"),
        ...     format="srt",
        ...     is_external=True,
        ...     file_path=FilePath("/movies/Movie.pt-BR.srt"),
        ... )
    """

    TEXT_FORMATS: ClassVar[frozenset[str]] = frozenset({"srt", "ass", "ssa", "vtt", "sub"})
    IMAGE_FORMATS: ClassVar[frozenset[str]] = frozenset({"pgs", "sup", "vobsub", "idx"})

    index: int = Field(ge=0)
    language: LanguageCode
    format: str
    title: str | None = None
    is_default: bool = False
    is_forced: bool = False
    is_external: bool = False
    file_path: FilePath | None = None

    @model_validator(mode="after")
    def validate_external_file_path(self) -> "SubtitleTrack":
        """Validate that external tracks have a file path.

        Returns:
            The validated track.

        Raises:
            ValueError: If external track has no file_path.
        """
        if self.is_external and self.file_path is None:
            raise ValueError("External subtitle track must have a file_path")
        return self

    @property
    def is_text_based(self) -> bool:
        """Check if subtitle is text-based (can be styled/searched).

        Returns:
            True for SRT, ASS, VTT formats; False for image-based (PGS, SUP).
        """
        return self.format.lower() in self.TEXT_FORMATS

    @property
    def is_image_based(self) -> bool:
        """Check if subtitle is image-based (bitmap).

        Returns:
            True for PGS, SUP, VOBSUB formats.
        """
        return self.format.lower() in self.IMAGE_FORMATS


__all__ = ["AudioTrack", "SubtitleTrack"]
