"""Tests for AddItemToCustomListUseCase."""

from unittest.mock import AsyncMock, Mock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_profile_viewing_policy_mock,
    make_visible_titles_lookup_mock,
)
from tests.modules.collections.unit.conftest import CollectionsUoWMocks, make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import AddItemToCustomListInput
from src.modules.collections.application.use_cases import AddItemToCustomListUseCase
from src.modules.collections.domain.entities import (
    MAX_ITEMS_PER_LIST,
    CustomList,
    CustomListItem,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")
_LIBRARY_ID = "lib_test12345678"
_MOVIE_ID = "mov_abc123def456"
_SERIES_ID = "ser_abc123def456"


def _create_list(name: str = "Test List", item_count: int = 0) -> CustomList:
    return CustomList.create(profile_id=_PROFILE_ID, name=name, existing_count=0).with_updates(
        item_count=item_count
    )


def _make_use_case(
    mocks: CollectionsUoWMocks,
    *,
    media_lookup: AsyncMock | None = None,
    policy_port: AsyncMock | None = None,
) -> AddItemToCustomListUseCase:
    return AddItemToCustomListUseCase(
        uow_factory=mocks.factory,
        media_lookup=media_lookup or make_visible_titles_lookup_mock(_MOVIE_ID, _SERIES_ID),
        profile_viewing_policy=policy_port or make_profile_viewing_policy_mock(_LIBRARY_ID),
    )


def _input(
    list_id: str,
    media_id: str = _MOVIE_ID,
    media_type: MediaType = MediaType.MOVIE,
) -> AddItemToCustomListInput:
    return AddItemToCustomListInput(
        profile_id=_PROFILE_ID.value, list_id=list_id, media_id=media_id, media_type=media_type
    )


@pytest.mark.unit
class TestAddItemToCustomListUseCase:
    """Tests for adding items to custom lists."""

    @pytest.mark.asyncio
    async def test_should_add_item_successfully(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        mock_repo.get_next_position.return_value = 0
        mock_repo.add_item.return_value = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
            position=0,
        )
        mock_repo.update.return_value = custom_list.increment_item_count()
        use_case = _make_use_case(mocks)

        await use_case.execute(
            AddItemToCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        mock_repo.add_item.assert_called_once()
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = None
        use_case = _make_use_case(mocks)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                    media_id="mov_abc123def456",
                    media_type=MediaType.MOVIE,
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_item_already_in_list(self) -> None:
        custom_list = _create_list(item_count=1)
        existing_item = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
        )
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = existing_item
        use_case = _make_use_case(mocks)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id=str(custom_list.id),
                    media_id="mov_abc123def456",
                    media_type=MediaType.MOVIE,
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_DUPLICATE"

    @pytest.mark.asyncio
    async def test_should_raise_when_list_is_full(self) -> None:
        custom_list = _create_list(item_count=MAX_ITEMS_PER_LIST)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        use_case = _make_use_case(mocks)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                AddItemToCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id=str(custom_list.id),
                    media_id="mov_abc123def456",
                    media_type=MediaType.MOVIE,
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_should_use_next_position(self) -> None:
        custom_list = _create_list(item_count=3)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_item.return_value = None
        mock_repo.get_next_position.return_value = 3
        mock_repo.add_item.return_value = CustomListItem.create(
            media_id="mov_abc123def456",
            media_type=MediaType.MOVIE,
            position=3,
        )
        mock_repo.update.return_value = custom_list.increment_item_count()
        use_case = _make_use_case(mocks)

        await use_case.execute(
            AddItemToCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            )
        )

        mock_repo.get_next_position.assert_called_once_with(str(custom_list.id), _PROFILE_ID)


@pytest.mark.unit
class TestAddItemToCustomListVisibilityGate:
    """Only a title the profile can see is added, and the refusal leaks nothing."""

    @pytest.mark.asyncio
    async def test_visible_title_is_added_after_asking_the_catalog_with_the_policy(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        mocks.custom_lists.get_next_position.return_value = 0
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)

        await _make_use_case(mocks, media_lookup=media_lookup, policy_port=policy_port).execute(
            _input(str(custom_list.id))
        )

        policy_port.find_for_profile.assert_awaited_once_with(_PROFILE_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[MovieId(_MOVIE_ID)],
            series_ids=[],
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
        )
        mocks.custom_lists.add_item.assert_awaited_once()
        mocks.custom_lists.update.assert_awaited_once_with(custom_list.increment_item_count())

    @pytest.mark.asyncio
    async def test_hidden_title_raises_404_and_writes_nothing(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(str(custom_list.id)))

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Movie", _MOVIE_ID)
        mocks.custom_lists.add_item.assert_not_awaited()
        mocks.custom_lists.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_someone_elses_list_answers_404_for_the_list_whatever_the_title(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input("lst_someoneelse0"))

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == (
            "CustomList",
            "lst_someoneelse0",
        )
        mocks.custom_lists.add_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hidden_title_already_in_the_list_is_404_not_duplicate(self) -> None:
        custom_list = _create_list(item_count=1)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = CustomListItem.create(
            media_id=_MOVIE_ID, media_type=MediaType.MOVIE
        )
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(str(custom_list.id)))

        assert exc_info.value.resource_type == "Movie"
        mocks.custom_lists.add_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hidden_title_on_a_full_list_is_404_not_limit(self) -> None:
        custom_list = _create_list(item_count=MAX_ITEMS_PER_LIST)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock())

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(str(custom_list.id)))

        assert exc_info.value.resource_type == "Movie"
        mocks.custom_lists.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deny_all_raises_404_without_asking_the_catalog(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        use_case = _make_use_case(
            mocks, media_lookup=media_lookup, policy_port=make_profile_viewing_policy_mock()
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(_input(str(custom_list.id)))

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Movie", _MOVIE_ID)
        media_lookup.find_visible_titles.assert_not_awaited()
        mocks.custom_lists.add_item.assert_not_awaited()
        mocks.custom_lists.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refusal_takes_the_type_from_the_id_prefix_not_the_body(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        media_lookup = make_visible_titles_lookup_mock()
        use_case = _make_use_case(mocks, media_lookup=media_lookup)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                _input(str(custom_list.id), _SERIES_ID, media_type=MediaType.MOVIE)
            )

        assert (exc_info.value.resource_type, exc_info.value.resource_id) == ("Series", _SERIES_ID)
        media_lookup.find_visible_titles.assert_awaited_once_with(
            movie_ids=[],
            series_ids=[SeriesId(_SERIES_ID)],
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
        )

    @pytest.mark.asyncio
    async def test_visible_title_already_in_the_list_is_still_duplicate(self) -> None:
        custom_list = _create_list(item_count=1)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = CustomListItem.create(
            media_id=_MOVIE_ID, media_type=MediaType.MOVIE
        )
        use_case = _make_use_case(mocks, media_lookup=make_visible_titles_lookup_mock(_MOVIE_ID))

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(_input(str(custom_list.id)))

        assert exc_info.value.message_code == "CUSTOM_LIST_ITEM_DUPLICATE"

    @pytest.mark.asyncio
    async def test_policy_and_visibility_are_read_before_the_list_transaction(self) -> None:
        custom_list = _create_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_item.return_value = None
        mocks.custom_lists.get_next_position.return_value = 0
        media_lookup = make_visible_titles_lookup_mock(_MOVIE_ID)
        policy_port = make_profile_viewing_policy_mock(_LIBRARY_ID)
        manager = Mock()
        manager.attach_mock(policy_port.find_for_profile, "policy")
        manager.attach_mock(media_lookup.find_visible_titles, "visibility")
        manager.attach_mock(mocks.factory, "uow")

        await _make_use_case(mocks, media_lookup=media_lookup, policy_port=policy_port).execute(
            _input(str(custom_list.id))
        )

        order = [
            name for name, _, _ in manager.mock_calls if name in {"policy", "visibility", "uow"}
        ]
        assert order == ["policy", "visibility", "uow"]

    @pytest.mark.asyncio
    async def test_missing_out_of_reach_and_above_limit_raise_the_same_error(self) -> None:
        """The refusal is built from the id alone, and never names a list item."""
        policies = {
            "missing": ViewingPolicy(allowed_library_ids=[_LIBRARY_ID]),
            "other_library": ViewingPolicy(allowed_library_ids=["lib_otherlibrary"]),
            "above_limit": ViewingPolicy(
                allowed_library_ids=[_LIBRARY_ID], maturity_limit=AgeRating(12)
            ),
        }
        custom_list = _create_list()
        errors: dict[str, ResourceNotFoundException] = {}
        for case, policy in policies.items():
            mocks = make_collections_uow_mock()
            mocks.custom_lists.find_by_id.return_value = custom_list
            mocks.custom_lists.find_item.return_value = None
            policy_port = make_profile_viewing_policy_mock()
            policy_port.find_for_profile.return_value = policy
            use_case = _make_use_case(
                mocks, media_lookup=make_visible_titles_lookup_mock(), policy_port=policy_port
            )
            with pytest.raises(ResourceNotFoundException) as exc_info:
                await use_case.execute(_input(str(custom_list.id)))
            errors[case] = exc_info.value

        attributes = ("resource_type", "resource_id", "code", "message_code", "message", "details")
        reference = errors["missing"]
        for error in errors.values():
            for attribute in attributes:
                assert getattr(error, attribute) == getattr(reference, attribute)
        assert (reference.resource_type, reference.message_code) == ("Movie", "MOVIE_NOT_FOUND")
