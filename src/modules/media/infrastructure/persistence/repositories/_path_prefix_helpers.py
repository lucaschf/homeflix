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
- Root-only inputs (``/``, ``\\``) are a special case: after stripping
  there's nothing left to anchor the ``LIKE`` on, so we keep the raw
  separator and use ``{sep}%`` directly — the separator itself is
  already the prefix we want.

Keeping this in one place means a change to the matching semantics
(e.g. case-insensitive comparison on Windows volumes) only has to
happen once.
"""

from collections.abc import Sequence

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute


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
        paths: Library root paths to match under. Empty entries are
            skipped; root-only entries (``"/"``) are kept as-is.

    Returns:
        A list of ``LIKE`` predicates, one per (path, separator) pair.
        Combine with ``sqlalchemy.or_`` at the call site.
    """
    filters: list[ColumnElement[bool]] = []
    for raw in paths:
        if not raw:
            continue
        stripped = raw.rstrip("/\\")
        if not stripped:
            # Root-only path: the raw value already ends with the
            # separator, so ``{raw}%`` is the correct anchor. Emitting
            # ``/{sep}%`` here would produce ``//%`` and match nothing.
            filters.append(column.like(f"{raw}%"))
            continue
        filters.append(column.like(f"{stripped}/%"))
        filters.append(column.like(f"{stripped}\\%"))
    return filters


__all__ = ["build_path_prefix_filters"]
