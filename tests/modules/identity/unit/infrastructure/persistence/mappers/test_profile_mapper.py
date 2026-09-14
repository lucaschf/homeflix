"""Unit tests for ProfileMapper's maturity_limit handling (ADR-035).

``None`` is the only stored value that means unrestricted, so a
corrupted column must decode to the most restrictive limit, never to
``None``. The mapper logs through structlog, which ``caplog`` does not
see, so the module logger is swapped for a recorder.
"""

import uuid
from typing import Any

import pytest

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.mappers import profile_mapper
from src.modules.identity.infrastructure.persistence.mappers.profile_mapper import (
    ProfileMapper,
    _decode_maturity_limit,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId

_PROFILE_EXTERNAL_ID = "prf_mapper000001"


class _RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **fields: Any) -> None:
        self.warnings.append((event, fields))


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingLogger:
    logger = _RecordingLogger()
    monkeypatch.setattr(profile_mapper, "_logger", logger)
    return logger


def _profile(limit: AgeRating | None) -> Profile:
    return Profile(
        id=ProfileId(_PROFILE_EXTERNAL_ID),
        user_id=UserId.generate(),
        name=ProfileName("Kid"),
        maturity_limit=limit,
    )


class TestDecodeMaturityLimit:
    def test_null_is_unrestricted_without_a_warning(self, recorder: _RecordingLogger):
        assert _decode_maturity_limit(_PROFILE_EXTERNAL_ID, None) is None
        assert recorder.warnings == []

    @pytest.mark.parametrize("raw", [0, 12, 21])
    def test_value_on_the_scale_decodes_as_is(self, recorder: _RecordingLogger, raw: int):
        assert _decode_maturity_limit(_PROFILE_EXTERNAL_ID, raw) == AgeRating(raw)
        assert recorder.warnings == []

    @pytest.mark.parametrize("raw", [99, 22, -1, "x", "12", 12.5, True])
    def test_corrupted_value_fails_closed_with_a_warning(
        self, recorder: _RecordingLogger, raw: object
    ):
        decoded = _decode_maturity_limit(_PROFILE_EXTERNAL_ID, raw)

        assert decoded is not None
        assert decoded == AgeRating(0)
        assert len(recorder.warnings) == 1
        _, fields = recorder.warnings[0]
        assert fields["profile_external_id"] == _PROFILE_EXTERNAL_ID
        assert fields["raw"] == raw


class TestProfileMapperMaturityLimit:
    def test_to_entity_reads_the_limit_column(self):
        model = ProfileModel(
            external_id=_PROFILE_EXTERNAL_ID,
            user_id=uuid.uuid4(),
            name="Kid",
            is_kids=False,
            maturity_limit=10,
            allowed_library_ids="[]",
        )

        entity = ProfileMapper.to_entity(model, user_external_id=UserId.generate().value)

        assert entity.maturity_limit == AgeRating(10)
        # The stored flag is never read back: it is derived from the limit.
        assert entity.is_kids is True

    @pytest.mark.parametrize(("limit", "is_kids"), [(None, False), (12, True), (14, False)])
    def test_to_model_writes_the_limit_and_the_derived_flag(self, limit, is_kids):
        model = ProfileMapper.to_model(
            _profile(None if limit is None else AgeRating(limit)), user_uuid=uuid.uuid4()
        )

        assert model.maturity_limit == limit
        assert model.is_kids is is_kids

    @pytest.mark.parametrize(("limit", "is_kids"), [(None, False), (10, True), (16, False)])
    def test_update_model_writes_the_limit_and_the_derived_flag(self, limit, is_kids):
        model = ProfileMapper.to_model(_profile(AgeRating(14)), user_uuid=uuid.uuid4())

        ProfileMapper.update_model(model, _profile(None if limit is None else AgeRating(limit)))

        assert model.maturity_limit == limit
        assert model.is_kids is is_kids
