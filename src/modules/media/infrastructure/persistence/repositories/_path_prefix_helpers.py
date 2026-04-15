r"""Shared ``LIKE`` prefix-filter builder for path-scoped count queries.

``MovieRepository.count_under_paths`` and
``SeriesRepository.count_under_paths`` both need to answer "rows whose
``file_path`` lives under any of these library paths?". The matching
rules are identical:

- Both ``/`` and ``\`` are treated as separators so a row written on
  one OS still matches a filter built on the other.
- The separator is appended explicitly (``{path}/%`` / ``{path}\\%``)
  rather than a bare ``{path}%`` so ``/media/movies`` doesn't swallow
  ``/media/movies-extra``.
- Trailing separators on the input (``/media/movies/`` vs
  ``/media/movies``) are normalized away so accidentally passing a
  trailing slash doesn't silently return zero.

Keeping this in one place means a change to the matching semantics
(e.g. case-insensitive comparison on Windows volumes) only has to
happen once.
"""

from collections.abc import Sequence

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute


def _normalize(path: str) -> str:
    """Strip trailing path separators so ``LIKE`` patterns stay well-formed."""
    return path.rstrip("/\\")


def build_path_prefix_filters(
    column: InstrumentedAttribute[str | None],
    paths: Sequence[str],
) -> list[ColumnElement[bool]]:
    """Build ``LIKE`` filters matching ``column`` values under any of ``paths``.

    Safe to pass user-visible library paths directly: values come from
    the Libraries API which only the owner can write to, and the
    trailing-separator normalization prevents minor formatting
    differences from producing empty result sets.

    Args:
        column: The ``file_path``-style column to filter.
        paths: Library root paths to match under. Empty entries and
            entries that reduce to empty after trimming are skipped.

    Returns:
        A list of ``LIKE`` predicates, one per (path, separator) pair.
        Combine with ``sqlalchemy.or_`` at the call site.
    """
    filters: list[ColumnElement[bool]] = []
    for raw in paths:
        path = _normalize(raw)
        if not path:
            continue
        filters.append(column.like(f"{path}/%"))
        filters.append(column.like(f"{path}\\%"))
    return filters


__all__ = ["build_path_prefix_filters"]
