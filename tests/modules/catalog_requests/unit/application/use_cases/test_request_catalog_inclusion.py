"""Tests for ``RequestCatalogInclusionUseCase``."""

import pytest

from src.modules.catalog_requests.application.dtos import (
    CreateCatalogRequestInput,
)
from src.modules.catalog_requests.application.use_cases import (
    RequestCatalogInclusionUseCase,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


@pytest.mark.unit
class TestRequestCatalogInclusionUseCase:
    """Tests for the "Solicitar inclusão" handler."""

    @pytest.mark.asyncio
    async def test_creates_request_when_none_exists(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        # ``add`` returns the persisted aggregate.
        mocks.catalog_requests.add.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                collection_tmdb_id=8091,
            ),
        )

        assert result.tmdb_id == 348
        assert result.collection_tmdb_id == 8091
        assert result.is_fulfilled is False
        assert result.notify_on_arrival is False
        mocks.catalog_requests.add.assert_called_once()
        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_repeat_returns_existing(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
            ),
        )

        assert result.id == str(existing.id)
        mocks.catalog_requests.add.assert_not_called()
        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_flips_notify_when_repeat_opts_in(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                notify_on_arrival=True,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_persists_title_on_new_request(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        mocks.catalog_requests.add.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                title="Alien",
            ),
        )

        assert result.title == "Alien"

    @pytest.mark.asyncio
    async def test_backfills_title_on_legacy_repeat(self) -> None:
        """Existing rows with ``title=None`` accept a backfill from a
        repeat submit so admin queue rendering recovers without an
        out-of-band migration step."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                title="Alien",
            ),
        )

        assert result.title == "Alien"
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_keeps_existing_title_on_repeat_without_payload(self) -> None:
        """A repeat submit that doesn't carry a title must not blank
        out an already-stored snapshot."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            title="Alien",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
            ),
        )

        assert result.title == "Alien"
        mocks.catalog_requests.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_requester_user_id_on_new_request(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        mocks.catalog_requests.add.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                requester_user_id="usr_abc123",
            ),
        )

        assert result.requester_user_id == "usr_abc123"

    @pytest.mark.asyncio
    async def test_backfills_requester_user_id_on_legacy_repeat(self) -> None:
        """Legacy rows with ``requester_user_id=None`` accept a
        backfill from a re-submit so notifications start landing in
        the user's inbox without an out-of-band migration."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                requester_user_id="usr_abc123",
            ),
        )

        assert result.requester_user_id == "usr_abc123"
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_owner_wins_when_second_user_submits(self) -> None:
        """First-owner-wins: user A's request keeps A as
        ``requester_user_id`` even when user B re-submits, so A's
        notification never gets re-routed to B."""
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            requester_user_id="usr_alice",
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        use_case = RequestCatalogInclusionUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateCatalogRequestInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                requester_user_id="usr_bob",
            ),
        )

        assert result.requester_user_id == "usr_alice"
        mocks.catalog_requests.update.assert_not_called()
