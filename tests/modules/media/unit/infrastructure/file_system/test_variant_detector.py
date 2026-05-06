"""Unit tests for VariantDetector."""

import pytest

from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector


@pytest.fixture
def detector() -> VariantDetector:
    return VariantDetector()


@pytest.mark.unit
class TestExtractBaseName:
    """Tests for VariantDetector.extract_base_name()."""

    def test_strips_resolution(self, detector: VariantDetector) -> None:
        assert detector.extract_base_name("Inception.2010.1080p.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.4K.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.720p.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.2160p.mkv") == "Inception.2010"

    def test_strips_source(self, detector: VariantDetector) -> None:
        assert detector.extract_base_name("Inception.2010.BluRay.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.WEB-DL.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.REMUX.mkv") == "Inception.2010"

    def test_strips_codec(self, detector: VariantDetector) -> None:
        assert detector.extract_base_name("Inception.2010.x264.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.HEVC.mkv") == "Inception.2010"

    def test_strips_hdr(self, detector: VariantDetector) -> None:
        assert detector.extract_base_name("Inception.2010.HDR.mkv") == "Inception.2010"
        assert detector.extract_base_name("Inception.2010.HDR10.mkv") == "Inception.2010"

    def test_strips_combined_tags(self, detector: VariantDetector) -> None:
        result = detector.extract_base_name(
            "Inception.2010.2160p.UHD.BluRay.REMUX.HEVC.DTS-HD.MA.mkv",
        )
        assert result == "Inception.2010"

    def test_handles_dashes_and_spaces(self, detector: VariantDetector) -> None:
        result = detector.extract_base_name("Inception 2010 1080p BluRay.mkv")
        assert result == "Inception 2010"

    def test_handles_full_path(self, detector: VariantDetector) -> None:
        result = detector.extract_base_name(
            "/movies/Inception.2010.1080p.BluRay.mkv",
        )
        assert result == "Inception.2010"

    def test_preserves_name_without_tags(self, detector: VariantDetector) -> None:
        assert detector.extract_base_name("my_video.mkv") == "my_video"


@pytest.mark.unit
class TestAreVariants:
    """Tests for VariantDetector.are_variants()."""

    def test_same_content_different_resolution(self, detector: VariantDetector) -> None:
        assert detector.are_variants(
            "Inception.2010.1080p.BluRay.mkv",
            "Inception.2010.4K.HDR.mkv",
        )

    def test_different_content(self, detector: VariantDetector) -> None:
        assert not detector.are_variants(
            "Inception.2010.1080p.mkv",
            "Interstellar.2014.1080p.mkv",
        )


@pytest.mark.unit
class TestGroupVariants:
    """Tests for VariantDetector.group_variants()."""

    def test_groups_by_base_name(self, detector: VariantDetector) -> None:
        files = [
            "Inception.2010.720p.mkv",
            "Inception.2010.1080p.mkv",
            "Inception.2010.4K.mkv",
            "Interstellar.2014.1080p.mkv",
        ]
        groups = detector.group_variants(files)

        assert len(groups) == 2
        assert len(groups["Inception.2010"]) == 3
        assert len(groups["Interstellar.2014"]) == 1

    def test_empty_list(self, detector: VariantDetector) -> None:
        assert detector.group_variants([]) == {}
