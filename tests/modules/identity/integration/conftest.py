"""Integration test fixtures for identity persistence."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Importing the identity models registers them on ``Base.metadata`` so the
# ``create_all`` call below knows about ``users``, ``profiles`` and
# ``access_tokens`` even though no test file references the modules directly.
import src.modules.identity.infrastructure.persistence.models  # noqa: F401
from src.infrastructure.persistence import Base
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)


@pytest.fixture(scope="function")
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Expose an ``async_sessionmaker`` bound to an in-memory SQLite database.

    ``StaticPool`` pins every connection to the same underlying SQLite
    instance so sessions opened from seeding fixtures and Units of Work
    under test see the same schema and rows.
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


@pytest.fixture(scope="function")
def uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyIdentityUnitOfWorkFactory:
    """Identity Unit of Work factory backed by the in-memory database."""
    return SqlAlchemyIdentityUnitOfWorkFactory(session_factory)
