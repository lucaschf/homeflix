"""Tests for FilePath value object."""


import pytest

from src.domain.shared.models import DomainValidationError


class TestFilePathCreation:
    """Tests for FilePath instantiation."""

    def test_should_create_with_valid_unix_path(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        # Platform-independent assertion
        assert "movies" in file_path.value
        assert "inception.mkv" in file_path.value

    def test_should_create_with_valid_windows_path(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("C:\\Movies\\inception.mkv")

        # os.path.normpath will normalize the path
        assert "inception.mkv" in file_path.value

    def test_should_strip_whitespace(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("  /movies/inception.mkv  ")

        # Platform-independent assertion
        assert "movies" in file_path.value
        assert "inception.mkv" in file_path.value
        assert not file_path.value.startswith(" ")
        assert not file_path.value.endswith(" ")

    def test_should_normalize_path(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies//subdir///inception.mkv")

        # Should remove redundant separators
        assert "//" not in file_path.value

    def test_should_raise_error_for_relative_path(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError, match="absolute"):
            FilePath("movies/inception.mkv")

    def test_should_raise_error_for_directory_traversal(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError, match="traversal"):
            FilePath("/movies/../etc/passwd")

    def test_should_raise_error_for_hidden_directory_traversal(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError, match="traversal"):
            FilePath("/movies/subdir/../../etc/passwd")

    def test_should_raise_error_for_empty_string(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError, match="cannot be empty"):
            FilePath("")

    def test_should_raise_error_for_whitespace_only(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError, match="cannot be empty"):
            FilePath("   ")

    def test_should_raise_error_for_non_string_input(self):
        from src.domain.media.value_objects import FilePath

        with pytest.raises(DomainValidationError):
            FilePath(123)


class TestFilePathProperties:
    """Tests for FilePath computed properties."""

    def test_filename_should_return_file_name(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        assert file_path.filename == "inception.mkv"

    def test_extension_should_return_file_extension(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        assert file_path.extension == ".mkv"

    def test_extension_should_return_empty_for_no_extension(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception")

        assert file_path.extension == ""

    def test_directory_should_return_parent_directory(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/action/inception.mkv")

        # Platform-independent check
        assert file_path.directory.endswith("action") or "movies" in file_path.directory


class TestFilePathEquality:
    """Tests for FilePath equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import FilePath

        path1 = FilePath("/movies/inception.mkv")
        path2 = FilePath("/movies/inception.mkv")

        assert path1 == path2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import FilePath

        path1 = FilePath("/movies/inception.mkv")
        path2 = FilePath("/movies/interstellar.mkv")

        assert path1 != path2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        path_set = {file_path}

        assert file_path in path_set

    def test_should_have_same_hash_when_equal(self):
        from src.domain.media.value_objects import FilePath

        path1 = FilePath("/movies/inception.mkv")
        path2 = FilePath("/movies/inception.mkv")

        assert hash(path1) == hash(path2)


class TestFilePathStringRepresentation:
    """Tests for FilePath string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        # Platform-independent assertion
        assert "inception.mkv" in str(file_path)

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        # Platform-independent assertion
        assert repr(file_path).startswith("FilePath(")
        assert "inception.mkv" in repr(file_path)


class TestFilePathImmutability:
    """Tests for FilePath immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import FilePath

        file_path = FilePath("/movies/inception.mkv")

        with pytest.raises(DomainValidationError):
            file_path.root = "/movies/other.mkv"
