"""End-to-end test scaffolding for the collections bounded context.

Mirrors the watch progress e2e setup: in-memory SQLite shared via
``StaticPool`` so seeds and HTTP-driven use cases see the same rows;
``ApplicationContainer`` wired by hand so the lifespan handler does not
run. The seeded profile carries a library ACL: the production
``ProfileViewingPolicyAdapter`` reads it, and an empty ACL would deny
everything.
"""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Registering collections, identity, media and watch progress models on
# ``Base.metadata`` so ``create_all`` discovers their tables.
import src.modules.collections.infrastructure.persistence.models
import src.modules.identity.infrastructure.persistence.models
import src.modules.media.infrastructure.persistence.models
import src.modules.watch_progress.infrastructure.persistence.models  # noqa: F401
from src.config.containers import ApplicationContainer
from src.infrastructure.persistence import Base
from src.main import WIRED_ROUTE_MODULES, create_app
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

LOGIN_PATH = "/api/v1/auth/cookie/login"


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
    """Handle for a seeded user and its single profile."""

    email: str
    password: str
    user_external_id: str
    profile_external_id: str


_password_hash = PasswordHash.recommended()


@pytest.fixture(scope="function")
def seed_user_with_profile(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[SeededUser]]:
    """Factory fixture: insert a verified member with one profile and its ACL."""

    async def _seed(
        *,
        allowed_library_ids: list[str],
        maturity_limit: int | None = None,
        email: str = "alice@example.com",
        password: str = "password-strong",
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
                is_superuser=False,
                role="member",
            )
            session.add(user)
            await session.flush()

            session.add(
                ProfileModel(
                    external_id=profile_external,
                    user_id=user.id,
                    name="Alice",
                    is_kids=False,
                    allowed_library_ids=json.dumps(allowed_library_ids),
                    maturity_limit=maturity_limit,
                )
            )
            await session.commit()

        return SeededUser(
            email=email,
            password=password,
            user_external_id=user_external,
            profile_external_id=profile_external,
        )

    return _seed


@pytest.fixture(scope="function")
def login_with_active_profile(
    client: AsyncClient,
    seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
) -> Callable[..., Awaitable[SeededUser]]:
    """Factory fixture: seed a user, log in and switch to its profile."""

    async def _login(
        *, allowed_library_ids: list[str], maturity_limit: int | None = None
    ) -> SeededUser:
        user = await seed_user_with_profile(
            allowed_library_ids=allowed_library_ids, maturity_limit=maturity_limit
        )
        login = await client.post(
            LOGIN_PATH,
            data={"username": user.email, "password": user.password},
        )
        assert login.status_code == 204
        switch = await client.post(f"/api/v1/profiles/{user.profile_external_id}/switch")
        assert switch.status_code == 204
        return user

    return _login
