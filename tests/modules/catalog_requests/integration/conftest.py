"""Integration test fixtures for catalog-requests database operations."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence import Base

# Import the BC models so they register on ``Base.metadata`` before
# ``create_all`` runs (otherwise the tables wouldn't be created).
from src.modules.catalog_requests.infrastructure.persistence.models import (  # noqa: F401
    CatalogRequestModel,
    CatalogSubscriptionModel,
)


@pytest.fixture(scope="function")
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Expose an ``async_sessionmaker`` bound to an in-memory SQLite database.

    ``StaticPool`` pins every connection to the same underlying SQLite
    instance so seed-time sessions and UoW-opened sessions see the
    same schema and rows.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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


@pytest.fixture(scope="function")
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Seed-time session sharing the ``session_factory`` engine."""
    async with session_factory() as session:
        yield session
