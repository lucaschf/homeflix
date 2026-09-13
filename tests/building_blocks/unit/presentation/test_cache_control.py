"""Tests for the JSON ``no-store`` cache policy middleware.

Each test mounts the middleware on a minimal FastAPI app with one route
returning the response under test, so the assertions cover the real
ASGI path — including error envelopes that the global exception handlers
build at route level, inside every user middleware.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse
from starlette.types import Message

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.presentation.cache_control import JsonNoStoreMiddleware
from src.building_blocks.presentation.exception_handlers import register_exception_handlers

_HLS_PLAYLIST = "application/vnd.apple.mpegurl"


def _make_app() -> FastAPI:
    """Build a FastAPI app with the middleware and the global error handlers."""
    app = FastAPI()
    app.add_middleware(JsonNoStoreMiddleware)
    register_exception_handlers(app)
    return app


def _get(app: FastAPI, path: str = "/probe") -> tuple[int, dict[str, str], bytes]:
    response = TestClient(app).get(path)
    return response.status_code, dict(response.headers), response.content


@pytest.mark.unit
class TestJsonResponses:
    """JSON without its own ``Cache-Control`` gains ``no-store``."""

    def test_should_add_no_store_to_json_200(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> dict[str, str]:
            return {"id": "mov_abc"}

        status, headers, _ = _get(app)

        assert status == 200
        assert headers["content-type"] == "application/json"
        assert headers["cache-control"] == "no-store"

    @pytest.mark.parametrize(
        "media_type",
        [
            "application/problem+json",
            "application/vnd.api+json",
            "application/json; charset=utf-8",
            "Application/JSON",
        ],
    )
    def test_should_add_no_store_to_any_json_media_type(self, media_type: str) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> Response:
            return Response(content=b"{}", media_type=media_type)

        _, headers, _ = _get(app)

        assert headers["cache-control"] == "no-store"

    def test_should_keep_cache_control_set_by_the_route(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> JSONResponse:
            return JSONResponse({"id": "mov_abc"}, headers={"Cache-Control": "private, max-age=60"})

        _, headers, _ = _get(app)

        assert headers["cache-control"] == "private, max-age=60"


@pytest.mark.unit
class TestErrorEnvelopes:
    """Envelopes built by the exception handlers pass back through the middleware."""

    def test_should_add_no_store_to_core_exception_envelope(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> None:
            raise ResourceNotFoundException.for_resource("Movie", "mov_missing")

        status, headers, _ = _get(app)

        assert status == 404
        assert headers["cache-control"] == "no-store"

    def test_should_add_no_store_to_http_exception_envelope(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        status, headers, _ = _get(app)

        assert status == 401
        assert headers["cache-control"] == "no-store"

    def test_should_add_no_store_to_validation_error_envelope(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route(limit: int) -> dict[str, int]:
            return {"limit": limit}

        status, headers, _ = _get(app, "/probe?limit=not-a-number")

        assert status == 422
        assert headers["cache-control"] == "no-store"


@pytest.mark.unit
class TestNonJsonResponses:
    """Anything that is not JSON is left exactly as the route built it."""

    @pytest.mark.parametrize(
        "media_type",
        ["image/jpeg", "text/vtt", _HLS_PLAYLIST, "application/x-ndjson"],
    )
    def test_should_not_add_cache_control_to_non_json(self, media_type: str) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> Response:
            return Response(content=b"payload", media_type=media_type)

        _, headers, _ = _get(app)

        assert "cache-control" not in headers

    def test_should_not_add_cache_control_to_plain_text(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> PlainTextResponse:
            return PlainTextResponse("ok")

        _, headers, _ = _get(app)

        assert "cache-control" not in headers

    def test_should_keep_no_cache_on_hls_playlist(self) -> None:
        app = _make_app()

        @app.get("/probe")
        async def _route() -> Response:
            return Response(
                content=b"#EXTM3U\n",
                media_type=_HLS_PLAYLIST,
                headers={"Cache-Control": "no-cache"},
            )

        _, headers, _ = _get(app)

        assert headers["cache-control"] == "no-cache"

    def test_should_not_add_cache_control_to_file_response(self, tmp_path: Path) -> None:
        segment = tmp_path / "segment_0001.ts"
        segment.write_bytes(b"\x47" * 188)
        app = _make_app()

        @app.get("/probe")
        async def _route() -> FileResponse:
            return FileResponse(str(segment), media_type="video/mp2t")

        status, headers, body = _get(app)

        assert status == 200
        assert body == b"\x47" * 188
        assert headers["content-type"] == "video/mp2t"
        assert "cache-control" not in headers

    async def test_should_stream_non_json_without_reading_the_body(self) -> None:
        """The client gets the first chunk before the route yields the last one.

        The generator refuses to finish until the first chunk has reached
        the client, so a middleware that drained the body before answering
        would deadlock and hit the timeout.
        """
        first_chunk_delivered = asyncio.Event()

        async def _chunks() -> AsyncIterator[bytes]:
            yield b"first"
            await first_chunk_delivered.wait()
            yield b"second"

        app = _make_app()

        @app.get("/probe")
        async def _route() -> StreamingResponse:
            return StreamingResponse(_chunks(), media_type="video/mp2t")

        sent: list[Message] = []
        request_delivered = False

        async def receive() -> Message:
            nonlocal request_delivered
            if not request_delivered:
                request_delivered = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()  # no disconnect until cancelled
            raise AssertionError("unreachable")

        async def send(message: Message) -> None:
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body") == b"first":
                first_chunk_delivered.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/probe",
            "raw_path": b"/probe",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        async with asyncio.timeout(5):
            await app(scope, receive, send)

        start = next(m for m in sent if m["type"] == "http.response.start")
        header_names = {name.lower() for name, _ in start["headers"]}
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        assert start["status"] == 200
        assert b"cache-control" not in header_names
        assert body == b"firstsecond"
