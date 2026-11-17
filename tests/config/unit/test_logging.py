"""Tests for the structlog configuration (``src.config.logging``).

Production logs are JSON and leave the host, so a rendered traceback
must never carry frame locals: request bodies and credentials live
there. structlog prints straight to stdout, which ``caplog`` does not
see, so the rendered lines are read from ``capsys``.
"""

import io
import json
import sys
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


class _FailingStream(io.StringIO):
    """A stdout whose writes fail, like a closed or broken pipe."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    def write(self, s: str) -> int:
        raise self._error


@pytest.mark.unit
@pytest.mark.usefixtures("json_logging")
class TestSinkFailures:
    """A line that cannot be written is dropped; the caller carries on.

    structlog prints straight to stdout. Unlike stdlib logging, which
    isolates sink errors in ``Handler.handleError``, a failed write raised
    into the code that was logging, so a request whose work had committed
    came back as a 500 because its log line could not be printed.
    """

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(BrokenPipeError(32, "Broken pipe"), id="broken-pipe"),
            pytest.param(ValueError("I/O operation on closed file."), id="closed-file"),
            pytest.param(UnicodeEncodeError("ascii", "é", 0, 1, "no ascii"), id="encoding"),
        ],
    )
    def test_should_not_raise_when_stdout_fails(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        monkeypatch.setattr(sys, "stdout", _FailingStream(error))

        get_logger().info("Custom list share revoked", list_id="lst_abc123def456")

    def test_should_report_the_dropped_line_on_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdout", _FailingStream(BrokenPipeError(32, "Broken pipe")))

        get_logger().info("Custom list share revoked", list_id="lst_abc123def456")

        assert "dropped a log line" in capsys.readouterr().err

    def test_should_still_write_to_a_working_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        get_logger().info("Custom list share revoked", list_id="lst_abc123def456")

        record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert record["event"] == "Custom list share revoked"
        assert record["list_id"] == "lst_abc123def456"
