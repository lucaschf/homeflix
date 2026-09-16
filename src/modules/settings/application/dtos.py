"""DTOs for settings use cases.

Inputs use plain ``str``/``dict`` so the application layer is callable
from any context (tests, CLI, HTTP routes) without forcing the caller
to import domain VOs. Use cases convert ``str`` → :class:`SettingKey`
and ``dict`` → :class:`ConfigVO` at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingDetail:
    """Read-model for a single setting bucket.

    Rows that have never been persisted are surfaced with
    ``source='default'`` and ``updated_at=None`` so the admin panel can
    distinguish "factory default" from "operator-edited" without making
    the field nullable on the domain entity.

    Attributes:
        key: Bucket identifier (matches :class:`SettingKey` value).
        value: VO payload as a JSON-friendly dict — what the API
            returns directly under ``data.value``.
        source: ``"migration_seed" | "admin" | "sql_override" |
            "default"``. ``"default"`` is synthesised by the use case
            when the row is absent.
        updated_by_user_id: External id of the operator that last
            wrote the row, or ``None`` for seeds / defaults.
        updated_at: ISO-8601 UTC timestamp of the last write, or
            ``None`` for synthesised defaults.
    """

    key: str
    value: dict[str, Any]
    source: str
    updated_by_user_id: str | None
    updated_at: str | None


@dataclass(frozen=True)
class AvatarLimits:
    """What a client needs to check an avatar before uploading it.

    Deliberately narrower than :class:`AvatarConfig`: ``storage_subdir``
    is a server filesystem path and stays on the admin surface.

    Attributes:
        max_size_bytes: The exact threshold the upload route refuses
            above, so a client applies the server's predicate instead of
            re-deriving it from megabytes and disagreeing on the factor.
        max_size_mb: The same cap as the admin panel states it, for a
            human-readable message.
        size_pixels: Side length of the square the upload is centre-
            cropped and scaled to, so a client can preview what it gets
            back rather than what it sent.
    """

    max_size_bytes: int
    max_size_mb: int
    size_pixels: int


@dataclass(frozen=True)
class UpdateSettingInput:
    """Input for :class:`UpdateSettingUseCase`.

    ``key`` is validated against :class:`SettingKey` by the use case.
    ``value`` is the full VO payload (full-replace semantics — the UI
    submits the entire form, not a partial patch).
    """

    key: str
    value: dict[str, Any]
    acting_admin_id: str


__all__ = ["AvatarLimits", "SettingDetail", "UpdateSettingInput"]
