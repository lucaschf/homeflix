"""End-to-end test scaffolding for the identity bounded context.

Builds a real ``FastAPI`` app, drives it with ``httpx.AsyncClient`` over
``ASGITransport`` (in-process, no real network), and points its
``IdentityUnitOfWork`` at an in-memory SQLite shared via ``StaticPool``
so seed fixtures and use cases under test see the same rows.

Lifespan is intentionally **not** entered — we wire the container and
populate ``app.state.container`` ourselves so each test starts with a
fresh, isolated database. ``container.infrastructure.session_factory``
is overridden via ``providers.Object`` so the FastAPI Users session
adapter and our ``IdentityUnitOfWork`` both go through the test
factory, sharing one in-memory DB per test.
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

# Importing the identity models registers them on ``Base.metadata`` so
# ``create_all`` discovers ``users`` / ``profiles`` / ``access_tokens``.
import src.modules.identity.infrastructure.persistence.models  # noqa: F401
from src.config.containers import ApplicationContainer
from src.infrastructure.persistence import Base
from src.main import WIRED_ROUTE_MODULES, create_app
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


@pytest.fixture(scope="function")
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """In-memory SQLite session factory bound to a shared connection.

    ``StaticPool`` is the load-bearing choice — without it every new
    connection sees a fresh empty ``:memory:`` DB and seed rows would
    disappear by the time the route handler queries.
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
    """Convenience handle returned by ``seed_user_with_profile``.

    Carries everything the test typically needs: the plain password
    (so it can hit ``/auth/cookie/login``), the prefixed external IDs
    (so it can assert they appear in API responses), and the email
    used as the login identifier.
    """

    email: str
    password: str
    user_external_id: str
    profile_external_id: str


# Hash the password with the same library FastAPI Users uses at login,
# so the verification step accepts what we seed.
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
            await session.flush()  # populate user.id (UUID)

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
