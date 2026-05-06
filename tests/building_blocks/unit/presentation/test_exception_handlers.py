"""Tests for the global exception handlers.

Wired through a minimal FastAPI app so we verify the actual HTTP
translation path (status, body, handler selection) rather than calling
the handlers directly with hand-rolled requests.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.building_blocks.infrastructure.errors import GatewayTimeoutException
from src.building_blocks.presentation.exception_handlers import (
    register_exception_handlers,
)


def _make_app() -> FastAPI:
    """Build a fresh FastAPI app with just the global handlers registered.

    Each test installs its own route so we can raise the exception of
    interest without coupling to domain modules.
    """
    app = FastAPI()
    register_exception_handlers(app)
    return app


@pytest.mark.unit
class TestCoreExceptionTranslation:
    """Typed exceptions flow through `core_exception_handler`."""

    def test_should_translate_resource_not_found_to_404(self) -> None:
        app = _make_app()

        @app.get("/movies/{movie_id}")
        async def _route(movie_id: str) -> dict[str, str]:
            raise ResourceNotFoundException.for_resource("Movie", movie_id)

        response = TestClient(app).get("/movies/mov_missing")

        assert response.status_code == 404
        body = response.json()
        assert body["type"] == "not_found_error"
        assert body["code"] == "RESOURCE_NOT_FOUND"

    def test_should_translate_use_case_validation_to_400(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise UseCaseValidationException.required_field("movie_id")

        response = TestClient(app).get("/foo")

        assert response.status_code == 400
        assert response.json()["type"] == "invalid_request_error"

    def test_should_translate_domain_validation_to_422(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise DomainValidationException(
                message="Bad state",
                message_code="INVALID_STATE",
                object_type="Movie",
            )

        response = TestClient(app).get("/foo")

        assert response.status_code == 422
        assert response.json()["type"] == "validation_error"

    def test_should_translate_business_rule_to_422(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise BusinessRuleViolationException(
                message="cannot toggle",
                rule_code="WATCHLIST_LIMIT_EXCEEDED",
            )

        response = TestClient(app).get("/foo")

        assert response.status_code == 422
        assert response.json()["code"] == "BUSINESS_RULE_VIOLATION"

    def test_should_translate_gateway_timeout_to_504(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise GatewayTimeoutException(
                message="TMDB timed out",
                gateway_name="TMDB",
                internal_message="connect timeout after 30s",
            )

        response = TestClient(app).get("/foo")

        assert response.status_code == 504
        body = response.json()
        assert body["type"] == "gateway_timeout_error"
        assert "internal_message" not in body  # never leaked to client


@pytest.mark.unit
class TestRequestValidation:
    """FastAPI validation errors surface as 422 in the envelope shape."""

    def test_should_return_structured_details_for_invalid_query(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route(age: int) -> dict[str, int]:
            return {"age": age}

        response = TestClient(app).get("/foo?age=not-a-number")

        assert response.status_code == 422
        body = response.json()
        assert body["type"] == "validation_error"
        assert body["code"] == "REQUEST_VALIDATION_ERROR"
        assert isinstance(body["details"], list)
        assert body["details"][0]["field"] == "age"


@pytest.mark.unit
class TestHttpExceptionTranslation:
    """`HTTPException` raised manually is wrapped in the envelope too."""

    def test_should_wrap_string_detail(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(status_code=404, detail="nope")

        response = TestClient(app).get("/foo")

        assert response.status_code == 404
        body = response.json()
        assert body == {
            "type": "not_found_error",
            "message": "nope",
            "code": "NOT_FOUND_ERROR",
        }

    def test_should_wrap_dict_detail(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(
                status_code=409,
                detail={"message": "duplicate", "code": "EMAIL_EXISTS"},
            )

        response = TestClient(app).get("/foo")

        assert response.status_code == 409
        body = response.json()
        assert body == {
            "type": "conflict_error",
            "message": "duplicate",
            "code": "EMAIL_EXISTS",
        }

    def test_should_ignore_caller_supplied_type_override(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(
                status_code=404,
                detail={"type": "attacker_injected", "message": "nope"},
            )

        response = TestClient(app).get("/foo")

        body = response.json()
        # envelope `type` is always derived from the HTTP status
        assert body["type"] == "not_found_error"

    def test_should_drop_unknown_keys_from_detail(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(
                status_code=400,
                detail={"message": "bad", "secret": "oops", "debug": {"sql": "..."}},
            )

        response = TestClient(app).get("/foo")

        body = response.json()
        assert "secret" not in body
        assert "debug" not in body
        assert body["message"] == "bad"

    def test_should_preserve_param_and_details_from_detail(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "bad field",
                    "code": "FIELD_INVALID",
                    "param": "email",
                    "details": {"expected": "string"},
                },
            )

        response = TestClient(app).get("/foo")

        body = response.json()
        assert body["param"] == "email"
        assert body["details"] == {"expected": "string"}

    def test_should_default_message_and_code_when_dict_detail_lacks_them(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise HTTPException(status_code=409, detail={"param": "email"})

        response = TestClient(app).get("/foo")

        body = response.json()
        assert body == {
            "type": "conflict_error",
            "param": "email",
            "message": "",
            "code": "CONFLICT_ERROR",
        }


@pytest.mark.unit
class TestUnhandledException:
    """Unexpected errors return a generic 500 without leaking details."""

    def test_should_return_generic_500_payload(self) -> None:
        app = _make_app()

        @app.get("/foo")
        async def _route() -> None:
            raise RuntimeError("secret stack trace 42")

        response = TestClient(app, raise_server_exceptions=False).get("/foo")

        assert response.status_code == 500
        body = response.json()
        assert body == {
            "type": "api_error",
            "message": "An unexpected error occurred.",
            "code": "INTERNAL_ERROR",
        }
