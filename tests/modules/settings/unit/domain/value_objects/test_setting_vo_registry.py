"""Tests for the SettingKey → configuration VO registry."""

import pytest

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.modules.settings.domain.value_objects import (
    SETTING_VO_TYPES,
    SettingKey,
    vo_type_for,
)


@pytest.mark.unit
class TestSettingVoRegistry:
    """The registry is the single source of truth for key → VO."""

    def test_every_setting_key_has_a_registered_vo(self) -> None:
        # Completeness guard: adding a SettingKey member without
        # registering its VO must fail here, not in production.
        missing = [key for key in SettingKey if key not in SETTING_VO_TYPES]

        assert missing == []

    def test_every_registered_vo_is_a_compound_value_object(self) -> None:
        non_compound = [
            key
            for key, vo_type in SETTING_VO_TYPES.items()
            if not issubclass(vo_type, CompoundValueObject)
        ]

        assert non_compound == []

    def test_every_registered_vo_is_default_constructible(self) -> None:
        # RuntimeSettings builds its fallback snapshot via ``vo_type()``;
        # a VO with a required field would break startup defaults.
        for vo_type in SETTING_VO_TYPES.values():
            vo_type()

    def test_vo_type_for_returns_registered_type(self) -> None:
        for key in SettingKey:
            assert vo_type_for(key) is SETTING_VO_TYPES[key]

    def test_registry_is_read_only(self) -> None:
        with pytest.raises(TypeError):
            SETTING_VO_TYPES[SettingKey.SCHEDULER] = object  # type: ignore[index]
