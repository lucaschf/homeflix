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
from src.modules.metadata.infrastructure.artwork_downloader import (
    HttpxArtworkDownloader,
)


class _FakeStreamResponse:
    def __init__(
        self,
        chunks: Sequence[bytes],
        headers: dict[str, str],
        status_error: Exception | None = None,
        is_redirect: bool = False,
        status_code: int = 200,
    ) -> None:
        self._chunks = chunks
        self.headers = headers
        self._status_error = status_error
        self.is_redirect = is_redirect
        self.status_code = status_code

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
    # Inject the fake through the constructor seam so a renamed internal
    # client can't silently bypass the fake into real network I/O.
    return HttpxArtworkDownloader(client=_FakeClient(ctx))  # type: ignore[arg-type]


_URL = "https://image.tmdb.org/t/p/original/x.png"


class TestFetch:
    async def test_should_return_bytes_and_content_type(self) -> None:
        ctx = _FakeStreamCtx(_FakeStreamResponse([b"ab", b"cd"], {"content-type": "image/png"}))
        downloader = _downloader_with(ctx)

        result = await downloader.fetch(_URL, max_bytes=1024)

        assert result.content == b"abcd"
        assert result.content_type == "image/png"

    async def test_should_return_none_content_type_when_header_absent(self) -> None:
        ctx = _FakeStreamCtx(_FakeStreamResponse([b"ab"], {}))
        downloader = _downloader_with(ctx)

        result = await downloader.fetch(_URL, max_bytes=1024)

        # Absent header -> None, not a fabricated octet-stream.
        assert result.content_type is None

    async def test_should_reject_disallowed_host_before_any_request(self) -> None:
        # A URL on a non-allow-listed host is refused before the client is
        # ever touched (SSRF guard). The fake would raise if reached.
        ctx = _FakeStreamCtx(enter_error=AssertionError("must not be requested"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch("https://evil.example.com/x.png", max_bytes=1024)

    async def test_should_reject_plaintext_http(self) -> None:
        ctx = _FakeStreamCtx(enter_error=AssertionError("must not be requested"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch("http://image.tmdb.org/x.png", max_bytes=1024)

    async def test_should_reject_a_redirect_response(self) -> None:
        ctx = _FakeStreamCtx(
            _FakeStreamResponse([], {"location": "https://image.tmdb.org/z"}, is_redirect=True)
        )
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch(_URL, max_bytes=1024)

    async def test_should_raise_when_body_exceeds_max_bytes(self) -> None:
        ctx = _FakeStreamCtx(
            _FakeStreamResponse([b"x" * 6, b"y" * 6], {"content-type": "image/jpeg"})
        )
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch(_URL, max_bytes=8)

    async def test_should_translate_timeout(self) -> None:
        ctx = _FakeStreamCtx(enter_error=httpx.TimeoutException("slow"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayTimeoutException):
            await downloader.fetch(_URL, max_bytes=1024)

    async def test_should_translate_http_status_error(self) -> None:
        request = httpx.Request("GET", _URL)
        response = httpx.Response(404, request=request)
        ctx = _FakeStreamCtx(
            _FakeStreamResponse(
                [],
                {"content-type": "text/html"},
                status_error=httpx.HTTPStatusError("not found", request=request, response=response),
            )
        )
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayBadResponseException):
            await downloader.fetch(_URL, max_bytes=1024)

    async def test_should_translate_transport_error(self) -> None:
        ctx = _FakeStreamCtx(enter_error=httpx.ConnectError("refused"))
        downloader = _downloader_with(ctx)

        with pytest.raises(GatewayUnavailableException):
            await downloader.fetch(_URL, max_bytes=1024)
