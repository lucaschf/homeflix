"""Tests for the VariantGroup parameter object."""

import pytest

from src.modules.media.application.ports.file_scanner_port import MediaType, ScannedFile
from src.modules.media.application.use_cases._variant_group import VariantGroup
from src.shared_kernel.value_objects.file_path import FilePath


def _scanned(path: str) -> ScannedFile:
    return ScannedFile(
        file_path=FilePath(path),
        file_size=1,
        media_type=MediaType.MOVIE,
        title="Movie",
    )


@pytest.mark.unit
class TestVariantGroup:
    def test_primary_is_first_and_additional_is_the_rest(self) -> None:
        a, b, c = _scanned("/m/a.mkv"), _scanned("/m/b.mkv"), _scanned("/m/c.mkv")
        group = VariantGroup.of([a, b, c])

        assert group.primary is a
        assert group.additional == (b, c)

    def test_paths_lists_every_variant_path(self) -> None:
        group = VariantGroup.of([_scanned("/m/a.mkv"), _scanned("/m/b.mkv")])

        assert group.paths == ["/m/a.mkv", "/m/b.mkv"]

    def test_iterates_in_order(self) -> None:
        files = [_scanned("/m/a.mkv"), _scanned("/m/b.mkv")]
        group = VariantGroup.of(files)

        assert list(group) == files

    def test_single_file_group_has_no_additional(self) -> None:
        only = _scanned("/m/a.mkv")
        group = VariantGroup.of([only])

        assert group.primary is only
        assert group.additional == ()

    def test_empty_group_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            VariantGroup.of([])
