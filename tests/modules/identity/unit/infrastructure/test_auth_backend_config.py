"""Tests that lock in the FastAPI Users authentication backend config.

These assertions are intentionally tight: any change to cookie name,
SameSite, HttpOnly, lifetime, or backend strategy is a security-relevant
shift (see ADR-011) and should require an explicit decision plus a
test update. Catches accidental edits.
"""

from src.modules.identity.infrastructure.auth.backend import (
    auth_backend,
    cookie_transport,
)


class TestCookieTransportConfig:
    def test_should_use_homeflix_session_cookie_name(self):
        assert cookie_transport.cookie_name == "homeflix_session"

    def test_should_set_httponly_so_javascript_cannot_read_the_cookie(self):
        assert cookie_transport.cookie_httponly is True

    def test_should_set_samesite_strict_for_csrf_mitigation(self):
        assert cookie_transport.cookie_samesite == "strict"

    def test_should_align_max_age_with_session_lifetime(self):
        # Default per ADR-011 is fixed 90 days.
        assert cookie_transport.cookie_max_age == 60 * 60 * 24 * 90


class TestAuthBackendConfig:
    def test_should_be_named_cookie_session(self):
        # The name appears in error responses and OpenAPI; locking it
        # avoids accidental renames that break clients.
        assert auth_backend.name == "cookie-session"

    def test_should_use_the_cookie_transport_singleton(self):
        assert auth_backend.transport is cookie_transport
