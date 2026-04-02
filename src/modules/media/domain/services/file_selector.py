"""File selection domain service."""

from src.modules.media.domain.value_objects.media_file import MediaFile
from src.modules.media.domain.value_objects.resolution import Resolution


class FileSelector:
    """Selects the best media file variant based on preferences.

    This domain service encapsulates the logic for choosing the best
    file variant from available options, considering resolution limits,
    HDR preferences, and bitrate as a tiebreaker.

    Example:
        >>> selector = FileSelector()
        >>> file = selector.select_file(
        ...     files=movie.files,
        ...     preferred_resolution=Resolution("1080p"),
        ...     max_resolution=None,
        ...     prefer_hdr=True,
        ... )
    """

    def select_file(
        self,
        files: list[MediaFile],
        preferred_resolution: Resolution | None = None,
        max_resolution: Resolution | None = None,
        prefer_hdr: bool = True,
    ) -> MediaFile | None:
        """Select the best file variant based on preferences.

        Selection priority:
        1. Filter by max_resolution (if defined)
        2. Match preferred_resolution (exact -> closest higher -> closest lower)
        3. Prioritize HDR (if prefer_hdr=True)
        4. Tiebreaker by highest video_bitrate

        Args:
            files: Available media file variants.
            preferred_resolution: Desired resolution; None for best available.
            max_resolution: Maximum allowed resolution; None for unlimited.
            prefer_hdr: Whether to prioritize HDR formats (default True).

        Returns:
            The best matching MediaFile, or None if no files are available.

        Example:
            >>> selector = FileSelector()
            >>> files = [file_720p, file_1080p, file_4k]
            >>> selector.select_file(files, Resolution("1080p"))
            file_1080p
        """
        if not files:
            return None

        candidates = list(files)

        # Step 1: filter by max resolution
        if max_resolution is not None:
            candidates = [
                f for f in candidates if f.resolution.total_pixels <= max_resolution.total_pixels
            ]
            if not candidates:
                return None

        # Step 2: match preferred resolution
        if preferred_resolution is not None:
            candidates = self._match_preferred(candidates, preferred_resolution)

        # Step 3: prioritize HDR
        if prefer_hdr:
            candidates = self._prioritize_hdr(candidates)

        # Step 4: tiebreaker by bitrate (highest wins)
        return max(candidates, key=lambda f: f.video_bitrate or 0)

    @staticmethod
    def _match_preferred(
        files: list[MediaFile],
        preferred: Resolution,
    ) -> list[MediaFile]:
        """Narrow candidates to the closest resolution to preferred.

        Resolution matching order:
        1. Exact match on preferred resolution
        2. Closest higher resolution (smallest upgrade)
        3. Closest lower resolution (largest downgrade)

        Args:
            files: Candidate files (already filtered by max_resolution).
            preferred: The desired resolution.

        Returns:
            Files matching the best available resolution tier.
        """
        preferred_pixels = preferred.total_pixels

        # Exact match
        exact = [f for f in files if f.resolution.total_pixels == preferred_pixels]
        if exact:
            return exact

        # Closest higher resolution
        higher = [f for f in files if f.resolution.total_pixels > preferred_pixels]
        if higher:
            best_pixels = min(f.resolution.total_pixels for f in higher)
            return [f for f in higher if f.resolution.total_pixels == best_pixels]

        # Closest lower resolution
        lower = [f for f in files if f.resolution.total_pixels < preferred_pixels]
        if lower:
            best_pixels = max(f.resolution.total_pixels for f in lower)
            return [f for f in lower if f.resolution.total_pixels == best_pixels]

        return files

    @staticmethod
    def _prioritize_hdr(files: list[MediaFile]) -> list[MediaFile]:
        """Filter to HDR files if any are available.

        Args:
            files: Candidate files.

        Returns:
            HDR files only if at least one exists, otherwise all files.
        """
        hdr_files = [f for f in files if f.hdr_format is not None]
        return hdr_files if hdr_files else files


__all__ = ["FileSelector"]
