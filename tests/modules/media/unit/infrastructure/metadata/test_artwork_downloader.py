"""Unit tests for :class:`HttpxArtworkDownloader` (ADR-029).

The httpx client is replaced with a fake that yields controlled chunks
and errors, so the tests exercise the adapter's streaming size cap and
its translation of transport failures into gateway exceptions without
real network I/O.
"""

from __future__ import annotations

from collections.abc import (  # noqa: TCH003 — runtime annotations on fakes
    AsyncIterator,
    Sequence,
)

import httpx
import pytest

from src.building_blocks.infrastructure.errors import (
    GatewayBadResponseException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.modules.media.infrastructure.metadata.artwork_downloader import (
    HttpxArtworkDownloader,
)


class _FakeStreamResponse:
    def __init__(
        self,
        chunks: Sequence[bytes],
        headers: dict[str, str],
        status_error: Exception | None = None,
    ) -> None:
        self._chunks = chunks
        self.headers = headers
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _FakeStreamCtx:
    def __init__(
        self,
        response: _FakeStreamResponse | None = None,
        enter_error: Exception | None = None,
    ) -> None:
        self._response = response
        self._enter_error = enter_error

    async def __aenter__(self) -> _FakeStreamResponse:
        if self._enter_error is not None:
            raise self._enter_error
        assert self._response is not None
        return self._response

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeClient:
    def __init__(self, ctx: _FakeStreamCtx) -> None:
        self._ctx = ctx

    def stream(self, _method: str, _url: str) -> _FakeStreamCtx:
        return self._ctx


def _downloader_with(ctx: _FakeStreamCtx) -> HttpxArtworkDownloader:
    downloader = HttpxArtworkDownloader()
    downloader._client = _FakeClient(ctx)  # type: ignore[assignment]
    return downloader


class TestFetch:
    async def test_should_return_bytes_and_content_type(self) -> None:
        ctx = _FakeStreamCtx(
            _FakeStreamResponse([b"ab", b"cd"], {"content-type": "image/png"})
        )
        downloader = _downloader_with(ctx)

        result = await downloader.fetch("https://x/y.png", max_bytes=1024)

        assert result.content == b"abcd"
        assert result.content_type == "image/png"

    async def test_should_raise_when_body_exceeds_max_bytes(self) -> None:
        ctx = _FakeStreamCtx(
            _FakeStreamResponse([b"x" * 6, b"y" * 6], {"content-type": "image/jpeg"})
        )
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch("https://x/big.jpg", max_bytes=8)

    async def test_should_translate_timeout(self) -> None:
        ctx = _FakeStreamCtx(enter_error=httpx.TimeoutException("slow"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayTimeoutException):
            await downloader.fetch("https://x/y.jpg", max_bytes=1024)

    async def test_should_translate_http_status_error(self) -> None:
        request = httpx.Request("GET", "https://x/y.jpg")
        response = httpx.Response(404, request=request)
        ctx = _FakeStreamCtx(
            _FakeStreamResponse(
                [],
                {"content-type": "text/html"},
                status_error=httpx.HTTPStatusError(
                    "not found", request=request, response=response
                ),
            )
        )
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch("https://x/y.jpg", max_bytes=1024)

    async def test_should_translate_transport_error(self) -> None:
        ctx = _FakeStreamCtx(enter_error=httpx.ConnectError("refused"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayUnavailableException):
            await downloader.fetch("https://x/y.jpg", max_bytes=1024)
