"""End-to-end test scaffolding for the catalog_requests BC.

Mirrors the settings/identity e2e setup: in-memory SQLite shared via
``StaticPool`` so seeds and HTTP-driven use cases see the same rows;
``ApplicationContainer`` wired by hand so the lifespan handler does not
run (no real scheduler boot under test).
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Register identity + catalog_requests models on ``Base.metadata`` so
# ``create_all`` discovers users / profiles / access_tokens /
# catalog_requests / catalog_subscriptions.
import src.modules.catalog_requests.infrastructure.persistence.models
import src.modules.identity.infrastructure.persistence.models  # noqa: F401
from src.config.containers import ApplicationContainer
from src.infrastructure.persistence import Base
from src.main import WIRED_ROUTE_MODULES, create_app
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


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


@dataclass(frozen=True)
class SeededUser:
    """Convenience handle for the member seed fixture."""

    email: str
    password: str
    user_external_id: str
    profile_external_id: str


_password_hash = PasswordHash.recommended()


@pytest.fixture(scope="function")
def seed_user_with_profile(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[SeededUser]]:
    """Factory fixture: insert a verified user + default profile."""

    async def _seed(
        *,
        email: str = "alice@example.com",
        password: str = "password-strong",
        profile_name: str = "Alice",
        is_admin: bool = False,
    ) -> SeededUser:
        user_external = UserId.generate().value
        profile_external = ProfileId.generate().value

        async with session_factory() as session:
            user = UserModel(
                external_id=user_external,
                email=email,
                hashed_password=_password_hash.hash(password),
                is_active=True,
                is_verified=True,
                is_superuser=is_admin,
                role="admin" if is_admin else "member",
            )
            session.add(user)
            await session.flush()

            profile = ProfileModel(
                external_id=profile_external,
                user_id=user.id,
                name=profile_name,
                is_kids=False,
            )
            session.add(profile)
            await session.commit()

        return SeededUser(
            email=email,
            password=password,
            user_external_id=user_external,
            profile_external_id=profile_external,
        )

    return _seed
