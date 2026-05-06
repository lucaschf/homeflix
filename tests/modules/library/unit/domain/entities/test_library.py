"""Tests for Library aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_name import LibraryName
from src.modules.library.domain.value_objects.library_type import LibraryType
from src.modules.library.domain.value_objects.metadata_provider import MetadataProviderConfig
from src.shared_kernel.value_objects.file_path import FilePath


class TestLibraryCreation:
    """Tests for Library instantiation."""

    def test_should_create_with_required_fields(self):
        library = Library(
            name=LibraryName("My Movies"),
            library_type=LibraryType.MOVIES,
            paths=[FilePath("/media/movies")],
        )

        assert library.name.value == "My Movies"
        assert library.library_type == LibraryType.MOVIES
        assert len(library.paths) == 1

    def test_should_create_with_string_values(self):
        library = Library(
            name="My Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        assert isinstance(library.name, LibraryName)
        assert isinstance(library.paths[0], FilePath)

    def test_should_default_language_to_english(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media"],
        )

        assert library.language.value == "en"

    def test_should_create_with_multiple_paths(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies", "/backup/movies"],
        )

        assert len(library.paths) == 2


class TestLibraryValidation:
    """Tests for Library validation."""

    def test_should_raise_error_for_empty_paths(self):
        with pytest.raises(DomainValidationException):
            Library(
                name="Movies",
                library_type=LibraryType.MOVIES,
                paths=[],
            )

    def test_should_raise_error_for_duplicate_paths(self):
        with pytest.raises(DomainValidationException, match="unique"):
            Library(
                name="Movies",
                library_type=LibraryType.MOVIES,
                paths=["/media/movies", "/media/movies"],
            )

    def test_should_raise_error_for_duplicate_provider_priorities(self):
        with pytest.raises(DomainValidationException, match="unique priorities"):
            Library(
                name="Movies",
                library_type=LibraryType.MOVIES,
                paths=["/media"],
                metadata_providers=[
                    MetadataProviderConfig.tmdb(priority=1),
                    MetadataProviderConfig.omdb(priority=1),
                ],
            )


class TestLibraryPathManagement:
    """Tests for Library path operations."""

    def test_with_path_should_add_new_path(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        library = library.with_path("/backup/movies")

        assert len(library.paths) == 2
        assert FilePath("/backup/movies") in library.paths

    def test_with_path_should_raise_error_for_duplicate(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        with pytest.raises(ValueError, match="already exists"):
            library.with_path("/media/movies")

    def test_without_path_should_remove_existing_path(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies", "/backup/movies"],
        )

        library = library.without_path("/backup/movies")

        assert len(library.paths) == 1

    def test_without_path_should_return_self_for_nonexistent(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        result = library.without_path("/other/path")

        assert result is library

    def test_without_path_should_raise_error_for_last_path(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        with pytest.raises(ValueError, match="last path"):
            library.without_path("/media/movies")


class TestLibraryMetadataProviders:
    """Tests for Library metadata provider operations."""

    def test_get_enabled_providers_should_return_sorted_by_priority(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media"],
            metadata_providers=[
                MetadataProviderConfig.omdb(priority=2),
                MetadataProviderConfig.tmdb(priority=1),
            ],
        )

        providers = library.get_enabled_providers()

        assert len(providers) == 2
        assert providers[0].priority == 1
        assert providers[1].priority == 2

    def test_get_enabled_providers_should_exclude_disabled(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media"],
            metadata_providers=[
                MetadataProviderConfig.tmdb(priority=1),
                MetadataProviderConfig(
                    provider=MetadataProviderConfig.omdb().provider,
                    priority=2,
                    enabled=False,
                ),
            ],
        )

        providers = library.get_enabled_providers()

        assert len(providers) == 1


class TestLibraryFactoryCreate:
    """Tests for Library.create() factory method."""

    def test_should_generate_id_automatically(self):
        library = Library.create(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media"],
        )

        assert library.id is not None
        assert library.id.prefix == "lib"

    def test_should_accept_string_library_type(self):
        library = Library.create(
            name="Movies",
            library_type="movies",
            paths=["/media"],
        )

        assert library.library_type == LibraryType.MOVIES

    def test_should_use_default_settings_if_not_provided(self):
        library = Library.create(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media"],
        )

        assert library.settings.preferred_audio_language.value == "en"


class TestLibrarySpecializedFactories:
    """Tests for specialized Library factory methods."""

    def test_create_movie_library_should_use_tmdb_and_omdb(self):
        library = Library.create_movie_library(
            name="Movies",
            paths=["/media/movies"],
        )

        assert library.library_type == LibraryType.MOVIES
        providers = library.get_enabled_providers()
        assert len(providers) == 2
        assert providers[0].provider.value == "tmdb"
        assert providers[1].provider.value == "omdb"

    def test_create_series_library_should_use_tvdb_and_tmdb(self):
        library = Library.create_series_library(
            name="TV Shows",
            paths=["/media/series"],
        )

        assert library.library_type == LibraryType.SERIES
        providers = library.get_enabled_providers()
        assert len(providers) == 2
        assert providers[0].provider.value == "tvdb"
        assert providers[1].provider.value == "tmdb"

    def test_create_anime_library_should_use_japanese_and_english_subs(self):
        library = Library.create_anime_library(
            name="Anime",
            paths=["/media/anime"],
        )

        assert library.library_type == LibraryType.SERIES
        assert library.language.value == "ja"
        assert library.settings.preferred_audio_language.value == "ja"
        assert library.settings.preferred_subtitle_language is not None
        assert library.settings.preferred_subtitle_language.value == "en"


class TestLibraryImmutability:
    """Tests for Library frozen (immutable) behavior."""

    def test_should_reject_direct_attribute_assignment(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        with pytest.raises(DomainValidationException):
            library.name = LibraryName("Changed")  # type: ignore[misc]

    def test_with_path_should_return_new_instance(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        updated = library.with_path("/backup/movies")

        assert updated is not library
        assert len(updated.paths) == 2
        assert len(library.paths) == 1

    def test_without_path_should_return_new_instance(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies", "/backup/movies"],
        )

        updated = library.without_path("/backup/movies")

        assert updated is not library
        assert len(updated.paths) == 1
        assert len(library.paths) == 2

    def test_without_path_nonexistent_should_return_self(self):
        library = Library(
            name="Movies",
            library_type=LibraryType.MOVIES,
            paths=["/media/movies"],
        )

        result = library.without_path("/other/path")

        assert result is library
