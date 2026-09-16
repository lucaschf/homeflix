"""Unit tests for the ``AvatarConfig`` value object."""

import pytest

from src.modules.settings.domain.value_objects import AvatarConfig


class TestMaxSizeBytes:
    """The single place megabytes become bytes."""

    @pytest.mark.parametrize("megabytes", [1, 2, 20])
    def test_should_derive_bytes_over_the_whole_configurable_range(self, megabytes: int):
        config = AvatarConfig(max_size_mb=megabytes)

        assert config.max_size_bytes == megabytes * 1024 * 1024

    def test_should_stay_out_of_the_persisted_payload(self):
        """A computed field would land in the ``app_settings`` row; a property does not.

        The bucket is stored as ``model_dump(mode="json")`` and read back
        through the same VO, so a derived key in the dump would be
        persisted once and then rejected on the next read.
        """
        dumped = AvatarConfig().model_dump(mode="json")

        assert "max_size_bytes" not in dumped
        assert AvatarConfig(**dumped) == AvatarConfig()
