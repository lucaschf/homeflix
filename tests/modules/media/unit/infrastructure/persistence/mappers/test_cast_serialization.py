"""Unit tests for cast_serialization helpers.

Covers the legacy-tolerant decode path so a regression in any one
branch (legacy ``list[str]``, dict without ``tmdb_id``, current dict
shape, malformed payloads) flips a test red.
"""

import pytest

from src.modules.media.domain.value_objects import CastMember
from src.modules.media.infrastructure.persistence.mappers.cast_serialization import (
    deserialize_cast,
    serialize_cast,
)


@pytest.mark.unit
class TestSerializeCast:
    def test_returns_none_for_empty_list(self) -> None:
        assert serialize_cast([]) is None

    def test_writes_full_dict_shape_with_tmdb_id(self) -> None:
        out = serialize_cast(
            [
                CastMember(
                    name="Leo",
                    profile_path="https://img/leo.jpg",
                    role="Cobb",
                    tmdb_id=6193,
                ),
            ],
        )
        assert out is not None
        assert '"name": "Leo"' in out
        assert '"tmdb_id": 6193' in out


@pytest.mark.unit
class TestDeserializeCast:
    def test_empty_input_returns_empty_list(self) -> None:
        assert deserialize_cast(None) == []
        assert deserialize_cast("") == []

    def test_legacy_list_of_strings(self) -> None:
        result = deserialize_cast('["Leo", "Joseph"]')

        assert [m.name for m in result] == ["Leo", "Joseph"]
        assert all(m.profile_path is None for m in result)
        assert all(m.tmdb_id is None for m in result)

    def test_dict_without_tmdb_id(self) -> None:
        result = deserialize_cast(
            '[{"name": "Leo", "profile_path": "https://img/leo.jpg", "role": "Cobb"}]',
        )

        assert len(result) == 1
        assert result[0].name == "Leo"
        assert result[0].profile_path == "https://img/leo.jpg"
        assert result[0].role == "Cobb"
        assert result[0].tmdb_id is None

    def test_dict_with_tmdb_id(self) -> None:
        result = deserialize_cast('[{"name": "Leo", "tmdb_id": 6193}]')

        assert result[0].tmdb_id == 6193

    def test_non_list_payload_collapses_to_empty(self) -> None:
        """Drift from a future migration or a manual DB edit could
        write a single object instead of a list. Without the guard,
        ``for item in items`` would iterate dict keys."""
        assert deserialize_cast('{"name": "Leo"}') == []

    def test_malformed_json_collapses_to_empty(self) -> None:
        """Truncated rows / corrupted blobs must not crash the read
        path. The encoder always writes valid JSON, but the column is
        just Text — anything could end up in there from a manual
        edit or a botched import."""
        assert deserialize_cast("not json at all") == []
        assert deserialize_cast('{"unterminated":') == []

    def test_dict_without_name_is_skipped(self) -> None:
        result = deserialize_cast(
            '[{"profile_path": "https://img/leo.jpg"}, {"name": "Joseph"}]',
        )

        assert [m.name for m in result] == ["Joseph"]

    def test_non_int_tmdb_id_is_dropped(self) -> None:
        """Strings, floats, or anything else where TMDB ids would be
        ints get silently dropped — the actor page falls back to a
        name-only lookup, no crash."""
        result = deserialize_cast('[{"name": "Leo", "tmdb_id": "6193"}]')

        assert result[0].tmdb_id is None
