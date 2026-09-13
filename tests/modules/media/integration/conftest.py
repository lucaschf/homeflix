"""Integration test fixtures for database operations."""

import importlib.util
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Registers ``movies`` / ``series`` with ``Base.metadata``: the FTS5
# migration reads both, so the search schema cannot rely on a test
# module having imported them first.
import src.modules.media.infrastructure.persistence.models  # noqa: F401
from src.infrastructure.persistence import Base

#: The newest migration that defines ``movies_fts`` / ``series_fts`` and
#: their sync triggers. Its ``upgrade()`` drops and recreates all eight
#: objects, so replaying it alone reproduces the head's search schema.
#: ``test_fts5_schema_fixture.py`` fails when a later migration takes over.
FTS5_MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "migrations"
    / "versions"
    / "2026_05_06_cover_remaining_fts5_fields.py"
)


@cache
def _fts5_migration() -> ModuleType:
    """Load the FTS5 migration module from its file path.

    Loaded lazily so a renamed migration fails only the tests that ask
    for the search schema, not every integration test at collection.
    """
    spec = importlib.util.spec_from_file_location("_fts5_schema_migration", FTS5_MIGRATION_PATH)
    if spec is None or spec.loader is None:
        msg = f"Could not load migration at {FTS5_MIGRATION_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_fts5_schema(connection: Connection) -> None:
    """Build the FTS5 search tables and triggers on a ``create_all`` schema.

    ``Base.metadata.create_all`` knows nothing about virtual tables, so
    this runs the migration's own ``upgrade()`` through a real Alembic
    ``Operations`` context instead of carrying a copy of its SQL that
    could drift from the head.

    Args:
        connection: A synchronous connection whose schema already holds
            the ``movies`` and ``series`` tables.
    """
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        _fts5_migration().upgrade()


@asynccontextmanager
async def _in_memory_session_factory(
    *schema_steps: Callable[[Connection], None],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield an ``async_sessionmaker`` over a fresh in-memory SQLite schema.

    Args:
        schema_steps: Synchronous callables run in order after
            ``create_all``, inside the same transaction.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for step in schema_steps:
            await conn.run_sync(step)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Expose an ``async_sessionmaker`` bound to an in-memory SQLite database.

    ``StaticPool`` pins every connection to the same underlying SQLite
    instance so seed-time sessions and UoW-opened sessions see the
    same schema and rows.
    """
    async with _in_memory_session_factory() as factory:
        yield factory


@pytest.fixture(scope="function")
async def fts_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Like ``session_factory``, plus the FTS5 search schema.

    Opt-in for tests that exercise ``search``: the virtual tables and
    their triggers come from the migration (see ``install_fts5_schema``),
    so rows written through the repositories are indexed exactly as in
    the application database.
    """
    async with _in_memory_session_factory(install_fts5_schema) as factory:
        yield factory


@pytest.fixture(scope="function")
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Seed-time session sharing the ``session_factory`` engine."""
    async with session_factory() as session:
        yield session
