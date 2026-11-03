"""Tests for list settings read from the environment (``src.config.settings``).

``.env.example`` documents these as comma-separated values. pydantic-settings
JSON-decodes list fields before any validator runs, so a list field without
``NoDecode`` rejects that documented form and the app does not start.
"""

import pytest

from src.config.settings import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:5173", ["http://localhost:5173"]),
        (
            "http://localhost:3000, http://localhost:5173",
            ["http://localhost:3000", "http://localhost:5173"],
        ),
    ],
)
def test_allowed_origins_accepts_the_documented_comma_separated_form(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    """``ALLOWED_ORIGINS`` in the ``.env.example`` format parses into a list."""
    monkeypatch.setenv("ALLOWED_ORIGINS", raw)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings init kwarg

    assert settings.allowed_origins == expected
