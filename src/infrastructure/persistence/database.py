"""Database configuration and session management.

This module provides async SQLAlchemy engine and session factory setup.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Database connection manager.

    Manages SQLAlchemy async engine and session factory lifecycle.

    Example:
        >>> db = Database("sqlite+aiosqlite:///./homeflix.db")
        >>> await db.connect()
        >>> async with db.session() as session:
        ...     # use session
        ...     pass
        >>> await db.disconnect()
    """

    def __init__(
        self,
        database_url: str,
        *,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        """Initialize database configuration.

        Args:
            database_url: SQLAlchemy async database URL.
            echo: If True, log all SQL statements.
            pool_size: Connection pool size (ignored for SQLite).
            max_overflow: Max connections above pool_size (ignored for SQLite).
        """
        self._database_url = database_url
        self._echo = echo
        self._pool_size = pool_size
        self._max_overflow = max_overflow

        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine.

        Returns:
            The async SQLAlchemy engine.

        Raises:
            RuntimeError: If not connected.
        """
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory.

        Returns:
            The async session factory.

        Raises:
            RuntimeError: If not connected.
        """
        if self._session_factory is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory

    async def connect(self) -> None:
        """Initialize database engine and session factory."""
        if self._engine is not None:
            return

        # SQLite doesn't support pool_size and max_overflow
        is_sqlite = self._database_url.startswith("sqlite")

        engine_kwargs: dict[str, object] = {
            "echo": self._echo,
        }

        if not is_sqlite:
            engine_kwargs["pool_size"] = self._pool_size
            engine_kwargs["max_overflow"] = self._max_overflow

        self._engine = create_async_engine(self._database_url, **engine_kwargs)

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def disconnect(self) -> None:
        """Close database connections and dispose engine."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Create a new database session context.

        Yields:
            An async database session.

        Raises:
            RuntimeError: If not connected.
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


__all__ = ["Database"]
