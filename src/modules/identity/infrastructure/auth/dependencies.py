"""FastAPI dependency chain for FastAPI Users.

Each dependency is a plain async function/generator suitable for use
as ``Depends(...)`` in routes. The chain is:

    Request
      -> get_async_session   (opens a session bound to the app container)
      -> get_user_db          (wraps session + UserModel)
      -> get_user_manager     (BaseUserManager[UserModel, UUID])
      -> auth_backend.get_strategy
         -> get_access_token_db -> get_database_strategy

This is FastAPI-native (not registered in the dependency-injector
container) because FastAPI Users assumes its own dependency style.
"""

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.modules.identity.domain.errors import NoActiveSessionError
from src.modules.identity.infrastructure.auth.user_manager import UserManager
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


def get_session_token(request: Request) -> str:
    """Return the opaque session token from the configured cookie.

    Single source of truth for the cookie name + missing-cookie error
    used both by ``get_current_profile`` and by routes that need the
    raw token (e.g. ``POST /profiles/{id}/switch``). Raises
    :class:`NoActiveSessionError` (HTTP 401) so the caller does not
    have to repeat the check.
    """
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        raise NoActiveSessionError(message="Session cookie missing")
    return token


async def get_async_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` bound to the app's container.

    Reads the session factory from ``app.state.container`` so it
    picks up the same engine the dependency-injector resolved for
    every other repository in the app.
    """
    session_factory = request.app.state.container.infrastructure.session_factory()
    async with session_factory() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[UserModel, uuid.UUID], None]:
    """Yield FastAPI Users' SQLAlchemy database adapter for ``UserModel``."""
    yield SQLAlchemyUserDatabase(session, UserModel)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    """Yield a ``UserManager`` instance for the current request."""
    yield UserManager(user_db)


async def get_access_token_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase[AccessTokenModel], None]:
    """Yield FastAPI Users' access-token DB adapter for the auth strategy."""
    yield SQLAlchemyAccessTokenDatabase(session, AccessTokenModel)


def get_database_strategy(
    access_token_db: SQLAlchemyAccessTokenDatabase = Depends(get_access_token_db),
) -> DatabaseStrategy:
    """Build the ``DatabaseStrategy`` consumed by ``auth_backend``."""
    settings = get_settings()
    return DatabaseStrategy(
        database=access_token_db,
        lifetime_seconds=settings.session_lifetime_seconds,
    )


__all__ = [
    "get_access_token_db",
    "get_async_session",
    "get_database_strategy",
    "get_user_db",
    "get_user_manager",
]
