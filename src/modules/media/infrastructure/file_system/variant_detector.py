"""Variant detection for grouping related media files."""

import re
from pathlib import PurePosixPath

from src.modules.media.application.ports.variant_detector_port import VariantDetectorPort

# Patterns stripped from filenames to get the base content name.
# Order matters: more specific patterns before generic ones.
_STRIP_PATTERNS = [
    # Resolution
    r"2160p",
    r"4[Kk]",
    r"UHD",
    r"1080[pi]",
    r"[Ff]ull\s*[Hh][Dd]",
    r"FHD",
    r"720p",
    r"[Hh][Dd]",
    r"480p",
    r"[Ss][Dd]",
    r"360p",
    # Source
    r"[Bb]lu[Rr]ay",
    r"BDRip",
    r"BRRip",
    r"WEB[-\s]?DL",
    r"WEB[-\s]?Rip",
    r"WEBRip",
    r"HDTV",
    r"DVDRip",
    r"REMUX",
    # HDR
    r"HDR10\+?",
    r"HDR",
    r"[Dd]olby\s*[Vv]ision",
    r"DV",
    r"HLG",
    # Video codec
    r"[Hh]\.?265",
    r"HEVC",
    r"[Hh]\.?264",
    r"[Xx]264",
    r"[Xx]265",
    r"AV1",
    r"VP9",
    r"MPEG4",
    # Audio codec
    r"DTS[-\s]?HD(?:[-\s.]MA)?",
    r"DTS",
    r"MA",
    r"TrueHD",
    r"Atmos",
    r"AAC",
    r"AC3",
    r"FLAC",
    r"EAC3",
    # Audio channels
    r"[257]\.[01]",
    # Misc tags
    r"PROPER",
    r"REPACK",
    r"EXTENDED",
    r"UNRATED",
    r"DC",
    r"IMAX",
    # Release group / quality tags in brackets or parentheses. The
    # parenthesis case deliberately skips a bare 4-digit year — ``(2002)``
    # vs ``(2025)`` is what distinguishes two same-titled movies, so the
    # year must stay in the base name or the scanner groups them as one
    # movie's variants (e.g. "Lilo & Stitch (2002)" + "(2025)").
    r"\[.*?\]",
    r"\((?![12]\d{3}\))[^)]*\)",
]

_COMBINED_PATTERN = re.compile(
    r"[\.\s_-](?:" + "|".join(_STRIP_PATTERNS) + r")(?=[\.\s_\-\[]|$)",
    re.IGNORECASE,
)


class VariantDetector(VariantDetectorPort):
    """Detect file variants of the same content based on filename patterns.

    Strips quality indicators (resolution, codec, source) from filenames
    to determine a base content name. Files with the same base name are
    considered variants of the same content.

    Example:
        >>> detector = VariantDetector()
        >>> detector.extract_base_name("Inception.2010.1080p.BluRay.mkv")
        'Inception.2010'
        >>> detector.are_variants(
        ...     "Inception.2010.1080p.BluRay.mkv",
        ...     "Inception.2010.4K.HDR.mkv",
        ... )
        True
    """

    def extract_base_name(self, file_path: str) -> str:
        """Extract the base content name from a filename.

        Strips resolution, codec, source, and other quality indicators
        to produce a normalized name for grouping.

        Args:
            file_path: File path or filename.

        Returns:
            Base content name with quality indicators removed.
        """
        # Normalize Windows separators so the stem isolates the filename
        # even when this code runs on POSIX against a path like ``D:\foo\bar.mkv``.
        name = PurePosixPath(file_path.replace("\\", "/")).stem

        # Strip quality-related tags
        result = _COMBINED_PATTERN.sub("", name)

        # Clean up trailing dots/dashes/underscores/spaces
        result = re.sub(r"[\.\s_-]+$", "", result)

        return result or name


__all__ = ["VariantDetector"]
