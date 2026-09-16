"""Unit tests for ``GetAvatarLimitsUseCase``."""

from dataclasses import asdict
from unittest.mock import AsyncMock

from src.modules.settings.application.use_cases import GetAvatarLimitsUseCase
from src.modules.settings.domain.value_objects import AvatarConfig


def _use_case(config: AvatarConfig) -> GetAvatarLimitsUseCase:
    reader = AsyncMock()
    reader.avatar.return_value = config
    return GetAvatarLimitsUseCase(avatar_config=reader)


class TestGetAvatarLimitsUseCase:
    async def test_should_project_the_fields_a_client_acts_on(self):
        use_case = _use_case(AvatarConfig(max_size_mb=5, size_pixels=512))

        limits = await use_case.execute()

        assert (limits.max_size_mb, limits.size_pixels) == (5, 512)

    async def test_should_report_the_byte_threshold_the_upload_enforces(self):
        # Not a re-derivation: the same expression the storage adapter
        # compares the payload against, so the two cannot drift.
        config = AvatarConfig(max_size_mb=7)
        use_case = _use_case(config)

        limits = await use_case.execute()

        assert limits.max_size_bytes == config.max_size_bytes

    async def test_should_not_carry_the_storage_subdir(self):
        """``storage_subdir`` is a server path; the member surface must not leak it."""
        use_case = _use_case(AvatarConfig(storage_subdir=".secret/avatars"))

        limits = await use_case.execute()

        assert set(asdict(limits)) == {"max_size_bytes", "max_size_mb", "size_pixels"}
