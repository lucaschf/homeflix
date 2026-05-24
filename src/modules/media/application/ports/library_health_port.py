"""Port for checking filesystem health of library roots + media files.

Used by the ADR-015 Phase 3 auto-merge detector: when a content-identity
collision is detected, the use case asks whether the *other* candidate's
file is still on disk and whether its library is mountable. A missing
file in a healthy library means "operator moved this elsewhere" — safe
to absorb silently into the freshly-enriched winner. A missing file in
an unmounted library means the I/O is transient — the safe call is to
fall back to the manual queue.

Returns plain ``bool`` because there is nothing else to carry; the
"no domain types in port returns" rule from ADR-009 holds — booleans
are primitive.

The adapter lives in ``media.infrastructure.acl`` and reads via the
Library UoW + ``pathlib.Path.exists``.
"""

from abc import ABC, abstractmethod


class LibraryHealthPort(ABC):
    """Check filesystem accessibility of library roots and media files."""

    @abstractmethod
    async def is_file_accessible(self, file_path: str) -> bool:
        """Return ``True`` when ``file_path`` exists on disk right now.

        Args:
            file_path: Absolute filesystem path as stored on the
                media entity. The port does not assume any prefix —
                it just checks ``Path(file_path).exists()``.

        Returns:
            ``True`` if the file exists, ``False`` otherwise. Callers
            should pair this with ``is_library_root_accessible`` before
            treating a ``False`` answer as "operator deleted this".
        """
        ...

    @abstractmethod
    async def is_library_root_accessible(self, library_id: str) -> bool:
        """Return ``True`` when the library's filesystem root is mounted.

        A library can declare multiple roots (``Library.paths``).
        Accessibility is "every declared root currently exists on
        disk" — partial mounts count as inaccessible because the
        scanner cannot give the operator a complete view. Missing
        libraries also count as inaccessible (the caller cannot
        decide "operator deleted this" against a phantom library).

        Args:
            library_id: Prefixed external id (``lib_xxx``).

        Returns:
            ``True`` when the library exists and every declared
            root path resolves on the filesystem.
        """
        ...


__all__ = ["LibraryHealthPort"]
