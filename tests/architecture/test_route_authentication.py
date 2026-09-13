"""Every HTTP route requires a session unless it is explicitly public.

There is no authentication middleware (``src/main.py``): a route is
protected only when its own dependency tree reaches one of identity's
session guards. A route that forgets to declare one is silently open to
anyone on the network — which is how the file-variant, library and
person-bio reads shipped anonymous while their write-side siblings were
admin-only.

This test walks ``app.routes`` and fails on any route whose dependency
tree reaches no guard and that is missing from ``_PUBLIC_ROUTES``, where
each entry must say why it is public. A new public route therefore needs
a deliberate, reviewed line here; a forgotten ``Depends`` fails CI.

The guard roots are ``current_active_user`` (FastAPI Users' cookie
check) and ``resolve_profile_id`` (session to active profile). Every
published guard composes on one of them through ``Depends`` —
``authenticated_user``, ``authenticated_admin``, ``current_admin_user``,
``get_current_profile`` — so the recursive walk finds the root through
any of them, including router-level ``dependencies=[...]``.

This is a guardrail on declarations, not a behavioural proof: a guard
invoked by hand inside a handler body is invisible to the walk, and a
dependency that happens to import a guard but never raises would pass.
The e2e suites own the 401/403 behaviour of each route.
"""

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from src.main import create_app
from src.modules.identity.infrastructure.auth import current_active_user
from src.modules.identity.presentation.public import (
    AuthenticatedUser,
    authenticated_admin,
    authenticated_user,
    resolve_profile_id,
)

_GUARDS = frozenset({current_active_user, resolve_profile_id})

#: Routes that are reachable without a session, and why.
_PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/"): "API banner: app name, version and docs link; no catalog or user data.",
    ("GET", "/health"): (
        "Liveness probe for process supervisors, which hold no session; returns only "
        "status, timestamp and version."
    ),
    ("GET", "/health/ready"): (
        "Readiness probe for process supervisors, which hold no session. Its probe "
        "messages can name library roots; tightening that is outside this guard."
    ),
    ("GET", "/openapi.json"): (
        "FastAPI serves the schema unconditionally; it describes routes, not data."
    ),
    ("POST", "/api/v1/auth/cookie/login"): (
        "Creates the session, so it cannot require one; there is no registration or "
        "first-run setup route."
    ),
    ("POST", "/api/v1/auth/cookie/logout"): (
        "Not actually anonymous: FastAPI Users guards it with its own "
        "``current_user_token`` dependency (401 without a session). That closure is "
        "built per router, so the walk cannot match it by identity."
    ),
    ("GET", "/api/v1/artwork/{key}"): (
        "Public by design (ADR-029, ADR-034): mirrored catalog imagery loaded by "
        "``<img>`` tags that cannot carry auth headers."
    ),
    ("GET", "/api/v1/stream/hls/{path_hash}/{file_path:path}"): (
        "HLS segment/sub-playlist delivery, gated separately by the pending ADR-036 "
        "signed URLs. Until that lands it is open: ADR-035 (Negative consequences) "
        "records that ``path_hash`` is a deterministic md5 with no secret or expiry."
    ),
}

#: FastAPI's interactive docs, mounted only when ``settings.debug`` is on.
#: Tolerated when present, not required, so the test holds in both modes.
_DEBUG_ONLY_PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/docs"): "Swagger UI over /openapi.json; debug builds only.",
    ("GET", "/docs/oauth2-redirect"): "Swagger UI OAuth2 helper page; debug builds only.",
    ("GET", "/redoc"): "ReDoc over /openapi.json; debug builds only.",
}


def _reaches_guard(dependant: Dependant) -> bool:
    """Whether any dependency in ``dependant``'s tree is a session guard."""
    return any(sub.call in _GUARDS or _reaches_guard(sub) for sub in dependant.dependencies)


def _endpoints(route: BaseRoute) -> set[tuple[str, str]]:
    """``(method, path)`` pairs served by ``route``.

    Starlette adds ``HEAD`` to every ``GET`` route; it is folded into the
    ``GET`` entry. A route without methods (websocket, mount) is reported
    as ``ANY`` so it cannot slip past the scan.
    """
    path = getattr(route, "path", repr(route))
    methods = set(getattr(route, "methods", None) or ())
    if not methods:
        return {("ANY", path)}
    if "GET" in methods:
        methods.discard("HEAD")
    return {(method, path) for method in methods}


def _is_guarded(route: BaseRoute) -> bool:
    return isinstance(route, APIRoute) and _reaches_guard(route.dependant)


def _open_endpoints(app: FastAPI) -> set[tuple[str, str]]:
    """Every endpoint of ``app`` whose route declares no session guard."""
    return {
        endpoint for route in app.routes if not _is_guarded(route) for endpoint in _endpoints(route)
    }


def _format(endpoints: set[tuple[str, str]]) -> str:
    return "\n".join(f"  {method} {path}" for method, path in sorted(endpoints))


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


@pytest.fixture(scope="module")
def open_endpoints(app: FastAPI) -> set[tuple[str, str]]:
    return _open_endpoints(app)


class TestEveryRouteRequiresASession:
    """The real app only exposes the allowlisted routes without a session."""

    def test_no_route_outside_the_allowlist_is_public(self, open_endpoints):
        unexpected = open_endpoints - _PUBLIC_ROUTES.keys() - _DEBUG_ONLY_PUBLIC_ROUTES.keys()

        assert not unexpected, (
            "These routes declare no session guard (authenticated_user, "
            "authenticated_admin, resolve_profile_id, ...). Add the guard, or, if "
            "the route is public by design, add it to _PUBLIC_ROUTES with the "
            "reason:\n" + _format(unexpected)
        )

    def test_allowlist_has_no_stale_entries(self, open_endpoints):
        """A route that gained a guard or was removed must leave the allowlist."""
        stale = _PUBLIC_ROUTES.keys() - open_endpoints

        assert not stale, "Drop these from _PUBLIC_ROUTES:\n" + _format(stale)

    def test_scan_reaches_the_application_routes(self, app):
        """A broken walk must fail loudly instead of passing on zero routes."""
        guarded = {
            endpoint for route in app.routes if _is_guarded(route) for endpoint in _endpoints(route)
        }

        assert {
            ("GET", "/api/v1/libraries"),
            ("GET", "/api/v1/libraries/{library_id}"),
            ("GET", "/api/v1/movies/{movie_id}/files"),
            ("GET", "/api/v1/series/episodes/{episode_id}/files"),
            ("GET", "/api/v1/people/{tmdb_id}"),
            ("GET", "/api/v1/movies/{movie_id}"),
        } <= guarded


class TestDetector:
    """The rule is only as strong as the dependency shapes the walk recognizes."""

    def test_classifies_direct_transitive_and_router_level_guards(self):
        router = APIRouter()

        @router.get("/open")
        async def open_route() -> None:
            ...

        @router.get("/member")
        async def member_route(
            _user: AuthenticatedUser = Depends(authenticated_user),
        ) -> None:
            ...

        @router.get("/admin")
        async def admin_route(
            _admin: AuthenticatedUser = Depends(authenticated_admin),
        ) -> None:
            ...

        @router.get("/profile")
        async def profile_route(profile_id: str = Depends(resolve_profile_id)) -> None:
            ...

        @router.get("/router-level", dependencies=[Depends(authenticated_admin)])
        async def router_level_route() -> None:
            ...

        app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
        app.include_router(router)

        assert _open_endpoints(app) == {("GET", "/open")}
