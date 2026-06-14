"""Unit tests for :class:`StreamingConfig` and :class:`HardwareAccel`."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import HardwareAccel, StreamingConfig


class TestStreamingConfig:
    def test_default_values(self) -> None:
        config = StreamingConfig()

        assert config.ffmpeg_threads is None
        assert config.hls_cache_max_size_mb == 5120
        assert config.hw_accel is HardwareAccel.AUTO

    def test_hw_accel_can_be_set(self) -> None:
        config = StreamingConfig(hw_accel=HardwareAccel.NVENC)

        assert config.hw_accel is HardwareAccel.NVENC

    def test_hw_accel_accepts_string_value(self) -> None:
        # The admin route binds the raw JSON body to the VO, so the enum
        # must validate from its string form.
        config = StreamingConfig.model_validate({"hw_accel": "off"})

        assert config.hw_accel is HardwareAccel.OFF

    def test_hw_accel_rejects_unknown_value(self) -> None:
        with pytest.raises(DomainValidationException):
            StreamingConfig(hw_accel="vaapi")  # type: ignore[arg-type]

    def test_missing_hw_accel_key_defaults_to_auto(self) -> None:
        # Backward compatibility: rows persisted before this field
        # existed have no ``hw_accel`` key and must rehydrate to AUTO.
        config = StreamingConfig.model_validate(
            {"ffmpeg_threads": 4, "hls_cache_max_size_mb": 2048}
        )

        assert config.hw_accel is HardwareAccel.AUTO

    def test_serialises_hw_accel_as_string(self) -> None:
        dumped = StreamingConfig(hw_accel=HardwareAccel.NVENC).model_dump(mode="json")

        assert dumped["hw_accel"] == "nvenc"
