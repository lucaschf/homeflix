"""Infrastructure layer dependency container.

Provides database connections, external API clients, and other
infrastructure components.
"""

from collections.abc import AsyncGenerator

from dependency_injector import containers, providers
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.building_blocks.infrastructure.in_process_event_bus import InProcessEventBus
from src.config.persistence.session_manager import create_tracked_session
from src.config.settings import Settings


async def _init_engine(
    database_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Create engine and session factory with lifecycle management."""
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs: dict[str, object] = {"echo": False}

    if is_sqlite:
        # SQLite: use NullPool to avoid connection limit issues
        engine_kwargs["poolclass"] = pool.NullPool
    else:
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10

    engine = create_async_engine(database_url, **engine_kwargs)

    # Auto-create tables only in dev (prod uses Alembic migrations)
    from src.config.settings import get_settings

    if get_settings().is_development:
        import src.modules.collections.infrastructure.persistence.models
        import src.modules.media.infrastructure.persistence.models
        import src.modules.watch_progress.infrastructure.persistence.models  # noqa: F401
        from src.config.persistence.base import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    yield factory

    await engine.dispose()


class InfrastructureContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for infrastructure dependencies."""

    config = providers.Dependency(instance_of=Settings)

    session_factory = providers.Resource(
        _init_engine,
        database_url=config.provided.database_url,
    )

    session = providers.Factory(
        create_tracked_session,
        factory=session_factory,
    )

    event_bus = providers.Singleton(InProcessEventBus)
