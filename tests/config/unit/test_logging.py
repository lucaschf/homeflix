"""Tests for the structlog configuration (``src.config.logging``).

Production logs are JSON and leave the host, so a rendered traceback
must never carry frame locals: request bodies and credentials live
there. structlog prints through ``PrintLoggerFactory``, which ``caplog``
does not see, so the rendered lines are read from ``capsys``.
"""

import json
from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.building_blocks.presentation.exception_handlers import register_exception_handlers
from src.config.logging import _setup_structlog, get_logger

_SECRET = "s3cret-pw-904518"
_ERROR_MESSAGE = "stored hash is corrupt"


@pytest.fixture
def json_logging() -> Iterator[None]:
    """Switch to the production JSON pipeline, restoring the previous one after."""
    previous = structlog.get_config()
    _setup_structlog(json_logs=True, log_level="INFO")
    yield
    structlog.configure(**previous)


def _hash_password(password: str) -> str:
    """Stand-in for a hasher that fails while the credential is a frame local."""
    raise ValueError(_ERROR_MESSAGE)


@pytest.mark.unit
@pytest.mark.usefixtures("json_logging")
class TestJsonTracebacks:
    """Exceptions logged in production keep their frames but not their locals."""

    def test_should_not_render_frame_locals(self, capsys: pytest.CaptureFixture[str]) -> None:
        try:
            _hash_password(_SECRET)
        except ValueError as exc:
            get_logger().error("Unhandled exception", exc_info=exc)

        out = capsys.readouterr().out

        assert _SECRET not in out
        record = json.loads(out.strip().splitlines()[-1])
        stack = record["exception"][0]
        assert stack["exc_type"] == "ValueError"
        assert stack["exc_value"] == _ERROR_MESSAGE
        frames = stack["frames"]
        assert frames[-1]["name"] == "_hash_password"
        assert all({"filename", "lineno", "name"} <= frame.keys() for frame in frames)
        assert all("locals" not in frame for frame in frames)

    def test_unhandled_exception_handler_should_keep_request_body_out_of_log(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        app = FastAPI()
        register_exception_handlers(app)

        @app.post("/login")
        async def _route(payload: dict[str, str]) -> None:
            _hash_password(payload["password"])

        response = TestClient(app, raise_server_exceptions=False).post(
            "/login", json={"password": _SECRET}
        )

        out = capsys.readouterr().out
        assert response.status_code == 500
        assert _SECRET not in out
        assert "Unhandled exception" in out
        assert _ERROR_MESSAGE in out
