"""Port for persisting profile avatar images outside the domain.

Profile avatars are user-uploaded files: the domain doesn't care
about disk paths, image decoding, or storage backends. The use
case talks to this port; the adapter under
``identity/infrastructure/storage/`` knows how to validate the
bytes, resize via Pillow, and write a WebP under the configured
``avatar_storage_subdir``.

A future S3 / object-store implementation would just be another
adapter satisfying the same contract — the port deliberately
returns a relative URL string rather than a filesystem path so
the domain never assumes the file lives on the local disk.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class InvalidAvatarImageError(Exception):
    """Raised when the uploaded bytes don't decode as a supported image.

    The use case translates this into HTTP 415 (Unsupported Media
    Type). Distinct from the size-check exception so the route can
    surface a precise error message.
    """


class AvatarTooLargeError(Exception):
    """Raised when the uploaded payload exceeds the configured cap.

    Translated by the use case into HTTP 413 (Payload Too Large).
    """


class AvatarStoragePort(ABC):
    """Persist or remove the bytes that back a profile's avatar."""

    @abstractmethod
    async def save(
        self,
        profile_id: str,
        *,
        content: bytes,
        declared_mime_type: str,
    ) -> str:
        """Validate, resize and persist the avatar image.

        Args:
            profile_id: Prefixed external id (``prf_xxx``) of the
                profile owning the avatar. Used as the storage key
                — re-uploading replaces the previous file.
            content: Raw bytes from the multipart upload. The
                adapter is responsible for verifying the bytes
                actually decode as an image (the declared MIME from
                the form is browser-supplied and not trusted).
            declared_mime_type: MIME the client claimed in the
                multipart part. Used as a hint for the allow-list
                check; the adapter still validates the actual bytes.

        Returns:
            The relative URL path the catalog should embed in
            ``Profile.avatar_url`` (e.g.
            ``/api/v1/profiles/prf_xxx/avatar?v=...``). Returning a
            URL keeps the domain unaware of where bytes actually
            live.

        Raises:
            InvalidAvatarImageError: When the bytes don't decode
                as a supported image (jpeg / png / webp).
            AvatarTooLargeError: When ``len(content)`` exceeds the
                configured ``avatar_max_size_mb`` cap.
        """
        ...

    @abstractmethod
    async def delete(self, profile_id: str) -> None:
        """Remove any persisted avatar for ``profile_id``.

        No-op when no avatar exists for the profile — the use case
        calls this on every avatar-delete and on every soft-delete
        of the profile, so the adapter MUST be idempotent.
        """
        ...


__all__ = [
    "AvatarStoragePort",
    "AvatarTooLargeError",
    "InvalidAvatarImageError",
]
