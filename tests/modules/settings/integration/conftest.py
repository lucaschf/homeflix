"""Integration-test fixtures for the settings BC."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence import Base
from src.modules.settings.infrastructure.persistence.models import (  # noqa: F401 — registers ``app_settings`` on Base.metadata
    SettingModel,
)


def _make_engine() -> AsyncEngine:
    """Build an in-memory SQLite engine that survives across sessions.

    ``sqlite:///:memory:`` opens a fresh DB per *connection*, so
    multiple sessions from the same engine see different schemas.
    ``StaticPool`` pins the engine to a single connection that all
    sessions share — required for the
    ``SqlAlchemySettingsUnitOfWorkFactory`` integration tests, where
    one UoW seeds a row and a separate UoW reads it back.
    """
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite session — one fresh schema per test."""
    engine = _make_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Session factory bound to a fresh in-memory SQLite engine."""
    engine = _make_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
