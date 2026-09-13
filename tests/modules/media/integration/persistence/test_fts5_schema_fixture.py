"""Guards the FTS5 search schema that ``fts_session_factory`` builds.

The fixture replays a single migration rather than the whole chain, on
the premise that the newest migration defining the search objects drops
and recreates all of them. That premise holds only until a later
migration takes over, so it is checked here against Alembic's own
revision order instead of being trusted.
"""

import re
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.modules.media.integration.conftest import FTS5_MIGRATION_PATH

_MIGRATIONS_DIR = Path(__file__).resolve().parents[5] / "migrations"

#: A statement that (re)defines one of the search objects — the virtual
#: tables or their ``movies_fts_*`` / ``series_fts_*`` sync triggers.
_FTS5_DDL = re.compile(
    r"CREATE\s+(?:VIRTUAL\s+TABLE|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:movies|series)_fts",
    re.IGNORECASE,
)

_SEARCH_OBJECTS_SQL = text(
    "SELECT type, name FROM sqlite_master "
    "WHERE (type = 'table' AND name IN ('movies_fts', 'series_fts')) "
    "OR (type = 'trigger' AND tbl_name IN ('movies', 'series'))"
)

_EXPECTED_SEARCH_OBJECTS = {
    ("table", "movies_fts"),
    ("table", "series_fts"),
    ("trigger", "movies_fts_insert"),
    ("trigger", "movies_fts_update"),
    ("trigger", "movies_fts_delete"),
    ("trigger", "series_fts_insert"),
    ("trigger", "series_fts_update"),
    ("trigger", "series_fts_delete"),
}


@pytest.mark.integration
class TestFts5SchemaFixture:
    """The fixture must build the head's search schema, and only on request."""

    def test_replays_the_newest_migration_that_defines_the_search_objects(self) -> None:
        """A newer FTS5 migration means the fixture is replaying a stale schema.

        Walks revisions from head to base and stops at the first one
        whose source (re)defines a search object. If this fails, point
        ``FTS5_MIGRATION_PATH`` at the migration named in the message.
        """
        scripts = ScriptDirectory(str(_MIGRATIONS_DIR)).walk_revisions()
        newest = next(
            Path(script.path)
            for script in scripts
            if _FTS5_DDL.search(Path(script.path).read_text(encoding="utf-8"))
        )

        assert newest == FTS5_MIGRATION_PATH, f"FTS5 schema is now defined by {newest.name}"

    async def test_builds_the_virtual_tables_and_sync_triggers(
        self, fts_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with fts_session_factory() as session:
            objects = set((await session.execute(_SEARCH_OBJECTS_SQL)).tuples().all())

        assert objects == _EXPECTED_SEARCH_OBJECTS

    async def test_leaves_the_default_schema_without_search_objects(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            objects = set((await session.execute(_SEARCH_OBJECTS_SQL)).tuples().all())

        assert objects == set()
