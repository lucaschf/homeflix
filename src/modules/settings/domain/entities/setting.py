"""Setting aggregate — one row per configuration bucket."""

from __future__ import annotations

from typing import Self

from pydantic import field_validator, model_validator

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.settings.domain.value_objects import (
    ConfigVO,
    SettingKey,
    SettingSource,
    vo_type_for,
)
from src.shared_kernel.value_objects import UserId  # — runtime for Pydantic


class Setting(AggregateRoot[SettingKey]):
    """Persisted snapshot of a configuration bucket.

    The aggregate's identity is the :class:`SettingKey` enum value —
    the same string used as the primary key in ``app_settings`` and as
    the URL slug under ``/admin/settings/<key>``. The ``value`` field
    carries the configuration VO whose type is dictated by ``id``; the
    aggregate validates this invariant on construction so the
    persistence layer can trust the in-memory shape without re-checking.

    Attributes:
        id: Which configuration bucket this row carries.
        value: The current configuration. Its concrete type must
            match the type registered for ``id`` in the
            ``setting_vo_registry`` (see :func:`vo_type_for`).
        source: Provenance of the value — migration seed, admin edit,
            or manual SQL override.
        updated_by_user_id: Identifier of the user that last wrote
            this setting via the admin panel. ``None`` for
            migration-seeded rows; may be ``None`` for ``SQL_OVERRIDE``
            rows if the operator did not fill it in.

    Example:
        >>> setting = Setting(
        ...     id=SettingKey.INTRO_DETECTION,
        ...     value=IntroDetectionConfig(enabled=True),
        ...     source=SettingSource.ADMIN,
        ...     updated_by_user_id="usr_abc123abcd00",
        ... )
        >>> updated = setting.with_updates(
        ...     value=setting.value.with_updates(min_confidence=0.85),
        ... )
    """

    id: SettingKey
    value: ConfigVO
    source: SettingSource
    updated_by_user_id: UserId | None = None

    @field_validator("updated_by_user_id", mode="before")
    @classmethod
    def _convert_updated_by(cls, v: str | UserId | None) -> UserId | None:
        """Accept a raw ``usr_xxx`` string (or ``None``) and validate the id."""
        if v is None or isinstance(v, UserId):
            return v
        return UserId(v)

    @model_validator(mode="after")
    def _validate_value_matches_key(self) -> Self:
        expected = vo_type_for(self.id)
        if not isinstance(self.value, expected):
            raise ValueError(
                f"Setting with key {self.id.value!r} requires value of type "
                f"{expected.__name__}, got {type(self.value).__name__}",
            )
        return self


__all__ = ["Setting"]
