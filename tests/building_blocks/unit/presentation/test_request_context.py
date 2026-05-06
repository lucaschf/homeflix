"""Tests for the per-request context middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.building_blocks.presentation.request_context import (
    RequestContextMiddleware,
    get_current_request_id,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/probe")
    async def _probe() -> dict[str, str | None]:
        return {"request_id": get_current_request_id()}

    return app


@pytest.mark.unit
class TestRequestContextMiddleware:
    """The middleware sets correlation id + timing headers."""

    def test_should_generate_request_id_when_missing(self) -> None:
        response = TestClient(_make_app()).get("/probe")

        header_id = response.headers["x-request-id"]
        body_id = response.json()["request_id"]
        assert header_id == body_id
        assert header_id.startswith("req_")

    def test_should_honour_inbound_request_id_header(self) -> None:
        response = TestClient(_make_app()).get(
            "/probe", headers={"X-Request-ID": "req_from-client"}
        )

        assert response.headers["x-request-id"] == "req_from-client"
        assert response.json()["request_id"] == "req_from-client"

    def test_should_emit_server_timing_header(self) -> None:
        response = TestClient(_make_app()).get("/probe")

        assert "server-timing" in response.headers
        assert response.headers["server-timing"].startswith("total;dur=")

    def test_should_clear_context_after_request(self) -> None:
        TestClient(_make_app()).get("/probe")

        assert get_current_request_id() is None
