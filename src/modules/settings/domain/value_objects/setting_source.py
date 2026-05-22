"""Provenance marker for a persisted setting row.

Used for audit: distinguishes values seeded once by the migration from
values an operator wrote via the admin panel and from manual SQL edits
made out-of-band.
"""

from enum import StrEnum


class SettingSource(StrEnum):
    """Where a setting value originated.

    Attributes:
        MIGRATION_SEED: Written by the one-time migration that introduced
            ``app_settings``. ``updated_by_user_id`` is ``None`` for rows
            with this source.
        ADMIN: Written via an admin-panel endpoint by an authenticated
            operator. ``updated_by_user_id`` must be set.
        SQL_OVERRIDE: Written via direct SQL (incident escape hatch).
            ``updated_by_user_id`` may or may not be set depending on
            whether the operator filled it in.
    """

    MIGRATION_SEED = "migration_seed"
    ADMIN = "admin"
    SQL_OVERRIDE = "sql_override"


__all__ = ["SettingSource"]
