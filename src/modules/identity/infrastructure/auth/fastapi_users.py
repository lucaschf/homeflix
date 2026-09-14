"""``FastAPIUsers`` singleton plus the auth dependencies.

Routes import ``current_active_user`` (or ``current_admin_user``) from
this module (or from the package
``src.modules.identity.infrastructure.auth``) and use it as
``Depends(...)`` to gate a route. ``current_admin_user`` layers a role
check on top of ``current_active_user`` so write-side endpoints
(library CRUD, scan, enrichment, intro markers, file management) stay
restricted to operators of the household, while regular members can
still hit read endpoints, watch progress, collections and profile
management.

Once the account has a parental PIN, the admin role alone is not enough:
``current_admin_user`` also asks the parental gate whether the session holds
admin authority (ADR-035, Amendment 7), and ``authenticated_user`` reports
``is_admin`` only when it does.
"""

import inspect
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request
from fastapi_users import FastAPIUsers

from src.building_blocks.application.errors import ForbiddenOperationException
from src.config.settings import get_settings
from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    GetAdminAccessInput,
)
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth.authenticated_user import AuthenticatedUser
from src.modules.identity.infrastructure.auth.backend import auth_backend
from src.modules.identity.infrastructure.auth.dependencies import get_user_manager
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

if TYPE_CHECKING:
    from src.modules.identity.application.use_cases.ensure_admin_authority import (
        EnsureAdminAuthorityUseCase,
    )
    from src.modules.identity.application.use_cases.get_admin_access import (
        GetAdminAccessUseCase,
    )

fastapi_users: FastAPIUsers[UserModel, uuid.UUID] = FastAPIUsers[UserModel, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def _build(provider: Any) -> Any:
    """Build a use case from an ``IdentityContainer`` provider.

    ``infrastructure.session_factory`` is a ``providers.Resource`` in
    production, so a provider that reaches it returns a Future; tests
    override it with ``providers.Object``, which returns synchronously.
    The ``isawaitable`` branch covers both, as in ``get_async_session``.
    The container is read from ``request.app.state`` rather than imported,
    because the container module imports this package.
    """
    built = provider()
    if inspect.isawaitable(built):
        built = await built
    return built


def _session_token(request: Request) -> str:
    """Return the session token the cookie transport authenticated.

    Not ``get_session_token``: a missing cookie there is a 401, which the web
    client reads as an expired session. The cookie is the only transport, so
    it is always present once ``current_active_user`` has passed; if it ever
    is not, the empty token matches no session and the gate suspends (403).
    """
    return request.cookies.get(get_settings().session_cookie_name, "")


def _admin_access_input(
    request: Request, user: UserModel, *, is_write: bool
) -> GetAdminAccessInput:
    """Describe an administrator's request to the admin-access use cases."""
    return GetAdminAccessInput(
        user_id=user.external_id,
        role=UserRole.ADMIN,
        parental_pin_configured=user.parental_pin_hash is not None,
        session_token=_session_token(request),
        is_write=is_write,
    )


async def current_admin_user(
    request: Request,
    user: UserModel = Depends(current_active_user),
) -> UserModel:
    """Require the authenticated user to hold admin authority on this session.

    Composes on top of ``current_active_user`` — the underlying chain
    still validates the cookie + active flag — and adds, in this order:

    1. The role check, before anything else, so a member learns nothing
       about the account's PIN and costs no query.
    2. Without a parental PIN the gate is inert: the admin passes with no
       query (ADR-035, Amendment 7 D2 — no limit exists without a PIN).
    3. With a PIN, the parental gate decides from the session's selected
       profile and unlock window, in exactly two queries. Writes
       (anything but ``GET``, ``HEAD`` and ``OPTIONS``) also need an unlock
       while any live profile of the account has a limit (D10). The unlock
       is read, never spent (D9).

    Every admin route passes through here, including the ones that depend on
    this guard directly rather than on ``authenticated_admin``.

    Raises:
        ForbiddenOperationException: When the authenticated user's
            role is not ``admin`` (HTTP 403 ``ADMIN_REQUIRED``).
        ParentalPinRequiredError: When the parental gate suspends the
            session's admin authority (HTTP 403, never 401).
    """
    if user.role != UserRole.ADMIN.value:
        raise ForbiddenOperationException(
            message="Admin role required",
            message_code="ADMIN_REQUIRED",
            required_permission="admin",
        )
    if user.parental_pin_hash is None:
        return user

    ensure: EnsureAdminAuthorityUseCase = await _build(
        request.app.state.container.identity.ensure_admin_authority,
    )
    await ensure.execute(
        _admin_access_input(request, user, is_write=request.method not in _READ_METHODS),
    )
    return user


async def authenticated_user(
    request: Request,
    user: UserModel = Depends(current_active_user),
) -> AuthenticatedUser:
    """Active caller as the ORM-free :class:`AuthenticatedUser`.

    The cross-BC counterpart of ``current_active_user`` — routes in other
    bounded contexts depend on this so they never import Identity's
    ``UserModel`` (ADR-009). Same cookie/active validation underneath.

    ``is_admin`` holds the admin role **and** admin read authority on this
    session: an administrator whose authority the parental gate suspends
    reads as a member. The gate is only consulted for an administrator
    whose account has a PIN.
    """
    is_admin = user.role == UserRole.ADMIN.value
    if is_admin and user.parental_pin_hash is not None:
        get_admin_access: GetAdminAccessUseCase = await _build(
            request.app.state.container.identity.get_admin_access,
        )
        access = await get_admin_access.execute(
            _admin_access_input(request, user, is_write=False),
        )
        is_admin = access is AdminAccessLevel.GRANTED
    return AuthenticatedUser(external_id=user.external_id, is_admin=is_admin)


async def authenticated_admin(
    user: UserModel = Depends(current_admin_user),
) -> AuthenticatedUser:
    """Admin caller as :class:`AuthenticatedUser`.

    Composes on ``current_admin_user``, which already enforced the role and
    the parental gate, and returns the published contract instead of the
    ORM. It does not ask the gate again: that would repeat its queries and
    evaluate the same request twice.
    """
    return AuthenticatedUser(external_id=user.external_id, is_admin=True)


__all__ = [
    "authenticated_admin",
    "authenticated_user",
    "current_active_user",
    "current_admin_user",
    "fastapi_users",
]
