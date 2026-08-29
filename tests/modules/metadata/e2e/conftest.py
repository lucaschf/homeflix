"""End-to-end test scaffolding for the metadata bounded context.

Mirrors the media e2e setup: an in-memory SQLite session factory shared
via ``StaticPool`` and an ``ApplicationContainer`` wired by hand so the
lifespan handler (real scheduler boot) does not fire under test. The
artwork proxy route is unauthenticated, so no user seeding is needed.
"""

from collections.abc import AsyncGenerator

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Registering identity + media models on ``Base.metadata`` so
# ``create_all`` discovers every table the wired container may touch.
import src.modules.identity.infrastructure.persistence.models
import src.modules.media.infrastructure.persistence.models  # noqa: F401
from src.config.containers import ApplicationContainer
from src.infrastructure.persistence import Base
from src.main import WIRED_ROUTE_MODULES, create_app


@pytest.fixture(scope="function")
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """In-memory SQLite session factory bound to a shared connection."""
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
def app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """FastAPI app wired against the in-memory test session factory."""
    container = ApplicationContainer()
    container.wire(modules=list(WIRED_ROUTE_MODULES))
    container.infrastructure.session_factory.override(
        providers.Object(session_factory),
    )

    fastapi_app = create_app()
    fastapi_app.state.container = container
    return fastapi_app


@pytest.fixture(scope="function")
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """In-process ``httpx`` client driving the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
