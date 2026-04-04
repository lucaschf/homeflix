"""Integration tests for Database class."""

import pytest

from src.config.persistence import Base
from src.config.persistence.database import Database


@pytest.mark.integration
class TestDatabase:
    """Integration tests for database connection management."""

    async def test_connect_creates_engine(self) -> None:
        """Test that connect initializes the engine."""
        db = Database("sqlite+aiosqlite:///:memory:")

        await db.connect()

        assert db._engine is not None
        assert db._session_factory is not None

        await db.disconnect()

    async def test_connect_is_idempotent(self) -> None:
        """Test that calling connect twice doesn't create new engine."""
        db = Database("sqlite+aiosqlite:///:memory:")

        await db.connect()
        engine1 = db._engine

        await db.connect()
        engine2 = db._engine

        assert engine1 is engine2

        await db.disconnect()

    async def test_disconnect_disposes_engine(self) -> None:
        """Test that disconnect cleans up resources."""
        db = Database("sqlite+aiosqlite:///:memory:")

        await db.connect()
        await db.disconnect()

        assert db._engine is None
        assert db._session_factory is None

    async def test_engine_property_raises_when_not_connected(self) -> None:
        """Test that engine property raises error when not connected."""
        db = Database("sqlite+aiosqlite:///:memory:")

        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.engine

    async def test_session_factory_property_raises_when_not_connected(self) -> None:
        """Test that session_factory property raises error when not connected."""
        db = Database("sqlite+aiosqlite:///:memory:")

        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.session_factory

    async def test_session_context_manager(self) -> None:
        """Test that session context manager works correctly."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()

        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with db.session() as session:
            assert session is not None
            # Session should auto-commit on exit

        await db.disconnect()

    async def test_session_rollback_on_exception(self) -> None:
        """Test that session rolls back on exception."""
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.connect()

        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        with pytest.raises(ValueError, match="test error"):
            async with db.session():
                raise ValueError("test error")

        await db.disconnect()

    async def test_database_with_echo_enabled(self) -> None:
        """Test database creation with echo parameter."""
        db = Database("sqlite+aiosqlite:///:memory:", echo=True)

        await db.connect()
        assert db._engine is not None

        await db.disconnect()

    async def test_database_with_pool_settings(self) -> None:
        """Test database ignores pool settings for SQLite."""
        db = Database(
            "sqlite+aiosqlite:///:memory:",
            pool_size=10,
            max_overflow=20,
        )

        await db.connect()
        # SQLite ignores pool settings, but shouldn't error
        assert db._engine is not None

        await db.disconnect()

    async def test_session_raises_when_not_connected(self) -> None:
        """Test that session() raises error when called before connect()."""
        db = Database("sqlite+aiosqlite:///:memory:")

        with pytest.raises(RuntimeError, match="Database not connected"):
            async with db.session():
                pass
