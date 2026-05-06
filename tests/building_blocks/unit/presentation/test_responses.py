"""Tests for the API response envelope helpers."""

import pytest

from src.building_blocks.presentation.responses import (
    Pagination,
    api_list,
    api_single,
)


@pytest.mark.unit
class TestApiSingle:
    """`api_single` wraps a resource in the v3.0 envelope."""

    def test_should_wrap_payload_with_declared_type(self) -> None:
        payload = {"id": "lib_1", "name": "Movies"}

        result = api_single("library", payload)

        assert result == {"type": "library", "data": payload}

    def test_should_accept_none_payload(self) -> None:
        result = api_single("progress", None)

        assert result == {"type": "progress", "data": None}

    def test_should_not_mutate_input_payload(self) -> None:
        payload: dict[str, object] = {"id": "mov_1"}

        api_single("movie", payload)

        assert payload == {"id": "mov_1"}


@pytest.mark.unit
class TestApiListMinimal:
    """Without pagination/filters, no metadata block is emitted."""

    def test_should_return_type_and_data_only(self) -> None:
        result = api_list([{"id": "mov_1"}])

        assert result == {"type": "list", "data": [{"id": "mov_1"}]}

    def test_should_accept_empty_list(self) -> None:
        result = api_list([])

        assert result == {"type": "list", "data": []}


@pytest.mark.unit
class TestApiListWithPagination:
    """Pagination nests under `metadata.pagination`."""

    def test_should_include_pagination_in_metadata(self) -> None:
        page = Pagination(has_more=True, next_cursor="cur_42")

        result = api_list([{"id": "mov_1"}], pagination=page)

        assert result["metadata"]["pagination"] == {
            "has_more": True,
            "next_cursor": "cur_42",
        }

    def test_should_omit_none_pagination_fields(self) -> None:
        page = Pagination(has_more=False)

        result = api_list([], pagination=page)

        assert result["metadata"]["pagination"] == {"has_more": False}

    def test_should_include_total_when_present(self) -> None:
        page = Pagination(has_more=False, total=123)

        result = api_list([], pagination=page)

        assert result["metadata"]["pagination"]["total"] == 123


@pytest.mark.unit
class TestApiListWithFilters:
    """Applied filters surface under `metadata.filters_applied`."""

    def test_should_include_filters_applied(self) -> None:
        result = api_list([], filters_applied={"genre": "drama"})

        assert result["metadata"]["filters_applied"] == {"genre": "drama"}

    def test_should_ignore_empty_filters(self) -> None:
        result = api_list([{"id": "mov_1"}], filters_applied={})

        assert "metadata" not in result


@pytest.mark.unit
class TestApiListWithExtras:
    """Arbitrary stable metadata extras merge into `metadata`."""

    def test_should_merge_extras_into_metadata(self) -> None:
        result = api_list(
            [],
            pagination=Pagination(has_more=False),
            metadata_extras={"total_count": 9},
        )

        assert result["metadata"]["total_count"] == 9
        assert result["metadata"]["pagination"] == {"has_more": False}


@pytest.mark.unit
class TestPaginationSerialization:
    """Pagination.to_dict omits None to keep the payload minimal."""

    def test_should_include_only_set_fields(self) -> None:
        page = Pagination(has_more=True, next_cursor="cur_1", prev_cursor="cur_0")

        assert page.to_dict() == {
            "has_more": True,
            "next_cursor": "cur_1",
            "prev_cursor": "cur_0",
        }

    def test_should_be_frozen(self) -> None:
        page = Pagination(has_more=False)

        with pytest.raises(AttributeError):
            page.has_more = True  # type: ignore[misc]
