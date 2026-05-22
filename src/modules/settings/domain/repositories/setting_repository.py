"""Repository contract for persisting :class:`Setting` aggregates."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import SettingKey


class SettingRepository(ABC):
    """Persistence port for the ``app_settings`` table.

    Only two operations are required for Phase 1 of ADR-013:

    - :meth:`list_all` to populate the :class:`RuntimeSettings`
      snapshot at startup and on TTL expiry.
    - :meth:`upsert` to apply admin-panel edits and migration seeds.

    Deletion is intentionally out of scope: removing a row falls back
    to the Pydantic ``Field`` default, which is the documented escape
    hatch for resetting a bucket to factory state. A future phase may
    add a ``delete`` method once the admin UI exposes a "reset to
    default" button.
    """

    @abstractmethod
    async def list_all(self) -> Sequence[Setting]:
        """Return every persisted setting row.

        The expected cardinality is small (at most one row per
        :class:`SettingKey`, ~5 today). Callers must tolerate any
        subset of keys being absent and fall back to the Pydantic
        defaults.
        """

    @abstractmethod
    async def find_by_key(self, key: SettingKey) -> Setting | None:
        """Return the row for ``key`` or ``None`` if absent."""

    @abstractmethod
    async def upsert(self, setting: Setting) -> Setting:
        """Insert ``setting`` or replace the existing row with the same key.

        Returns the persisted entity with any DB-managed fields
        (``created_at``, ``updated_at``) refreshed.
        """


__all__ = ["SettingRepository"]
