"""Tests for MetadataProvider and MetadataProviderConfig."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.library.domain.value_objects.metadata_provider import (
    MetadataProvider,
    MetadataProviderConfig,
)


class TestMetadataProvider:
    """Tests for MetadataProvider enum."""

    def test_should_have_tmdb(self):
        assert MetadataProvider.TMDB.value == "tmdb"

    def test_should_have_omdb(self):
        assert MetadataProvider.OMDB.value == "omdb"

    def test_should_have_tvdb(self):
        assert MetadataProvider.TVDB.value == "tvdb"

    def test_should_create_from_string(self):
        provider = MetadataProvider("tmdb")

        assert provider == MetadataProvider.TMDB

    def test_should_have_three_providers(self):
        assert len(MetadataProvider) == 3


class TestMetadataProviderConfigCreation:
    """Tests for MetadataProviderConfig instantiation."""

    def test_should_create_with_valid_values(self):
        config = MetadataProviderConfig(
            provider=MetadataProvider.TMDB,
            priority=1,
            enabled=True,
        )

        assert config.provider == MetadataProvider.TMDB
        assert config.priority == 1
        assert config.enabled is True

    def test_should_default_enabled_to_true(self):
        config = MetadataProviderConfig(
            provider=MetadataProvider.TMDB,
            priority=1,
        )

        assert config.enabled is True

    def test_should_accept_priority_1_to_10(self):
        for priority in range(1, 11):
            config = MetadataProviderConfig(
                provider=MetadataProvider.TMDB,
                priority=priority,
            )
            assert config.priority == priority


class TestMetadataProviderConfigValidation:
    """Tests for MetadataProviderConfig validation."""

    def test_should_raise_error_for_priority_zero(self):
        with pytest.raises(DomainValidationException):
            MetadataProviderConfig(
                provider=MetadataProvider.TMDB,
                priority=0,
            )

    def test_should_raise_error_for_priority_above_10(self):
        with pytest.raises(DomainValidationException):
            MetadataProviderConfig(
                provider=MetadataProvider.TMDB,
                priority=11,
            )

    def test_should_raise_error_for_negative_priority(self):
        with pytest.raises(DomainValidationException):
            MetadataProviderConfig(
                provider=MetadataProvider.TMDB,
                priority=-1,
            )


class TestMetadataProviderConfigFactories:
    """Tests for MetadataProviderConfig factory methods."""

    def test_tmdb_factory_should_create_tmdb_config(self):
        config = MetadataProviderConfig.tmdb()

        assert config.provider == MetadataProvider.TMDB
        assert config.priority == 1
        assert config.enabled is True

    def test_tmdb_factory_should_accept_custom_priority(self):
        config = MetadataProviderConfig.tmdb(priority=3)

        assert config.priority == 3

    def test_omdb_factory_should_create_omdb_config(self):
        config = MetadataProviderConfig.omdb()

        assert config.provider == MetadataProvider.OMDB
        assert config.priority == 2

    def test_tvdb_factory_should_create_tvdb_config(self):
        config = MetadataProviderConfig.tvdb()

        assert config.provider == MetadataProvider.TVDB
        assert config.priority == 1
