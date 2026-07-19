"""Tests for the application entry point (src.main)."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from src.main import _resolve_version


@pytest.mark.unit
class TestResolveVersion:
    """Tests for the app-version resolver backing OpenAPI + health."""

    def test_should_return_package_metadata_version(self) -> None:
        # The version is sourced from installed distribution metadata so
        # the OpenAPI schema and /health never drift from pyproject.
        with patch("src.main.version", return_value="1.2.3"):
            assert _resolve_version() == "1.2.3"

    def test_should_fall_back_when_package_not_installed(self) -> None:
        # Running as a bare script (no installed distribution) resolves to
        # a clear sentinel rather than a stale hardcoded number.
        with patch("src.main.version", side_effect=PackageNotFoundError):
            assert _resolve_version() == "0.0.0"
