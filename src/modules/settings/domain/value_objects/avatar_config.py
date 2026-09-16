"""Avatar upload tunables — output location and image sizing."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class AvatarConfig(CompoundValueObject):
    """Operational knobs for profile-avatar uploads.

    Attributes:
        storage_subdir: Subdirectory (relative to the thumbnails
            directory) where uploaded profile avatars are stored.
            Created on first upload; the operator can change this
            without manual filesystem migration as long as the new
            path is empty.
        max_size_mb: Maximum accepted upload size in megabytes.
            Uploads above this cap are rejected with HTTP 413 before
            the image is decoded. 2 MB is comfortably above what a
            phone camera produces after browser-side compression and
            well below what a laptop would happily upload over a slow
            connection.
        size_pixels: Final square side length (in pixels) of the
            resized avatar. The uploaded image is centre-cropped to a
            square and scaled to this size before being persisted as
            WebP. 256 is the size the picker and AccountMenu render at
            1x; bumping it would let those surfaces render crisper at
            2x / 3x pixel density.

    Example:
        >>> cfg = AvatarConfig(size_pixels=512)
    """

    storage_subdir: str = Field(default=".homeflix/avatars", min_length=1)
    max_size_mb: int = Field(default=2, ge=1, le=20)
    size_pixels: int = Field(default=256, ge=64, le=1024)

    @property
    def max_size_bytes(self) -> int:
        """The cap in bytes — the exact threshold an upload is refused above.

        The one place megabytes become bytes, so the limit a client is
        told and the limit the storage adapter enforces cannot drift
        apart. A plain ``@property`` on purpose: a computed field would
        enter ``model_dump()`` and land in the persisted setting row.

        Returns:
            :attr:`max_size_mb` in binary megabytes.
        """
        return self.max_size_mb * 1024 * 1024


__all__ = ["AvatarConfig"]
