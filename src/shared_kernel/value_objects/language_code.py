"""Language code value object (ISO 639-1)."""

import re
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject


class LanguageCode(StringValueObject):
    """ISO 639-1 two-letter language code.

    Used for specifying preferred languages for metadata, audio tracks,
    and subtitles.

    Attributes:
        COMMON_CODES: Set of commonly used language codes for validation hints.

    Example:
        >>> lang = LanguageCode("en")
        >>> lang.value
        'en'
        >>> LanguageCode("PT").value  # Normalized to lowercase
        'pt'
    """

    # Common language codes (not exhaustive, just for documentation)
    COMMON_CODES: ClassVar[frozenset[str]] = frozenset(
        {
            "en",  # English
            "pt",  # Portuguese
            "es",  # Spanish
            "fr",  # French
            "de",  # German
            "it",  # Italian
            "ja",  # Japanese
            "ko",  # Korean
            "zh",  # Chinese
            "ru",  # Russian
            "ar",  # Arabic
            "hi",  # Hindi
            "nl",  # Dutch
            "pl",  # Polish
            "sv",  # Swedish
            "no",  # Norwegian
            "da",  # Danish
            "fi",  # Finnish
            "tr",  # Turkish
            "th",  # Thai
            "vi",  # Vietnamese
            "id",  # Indonesian
            "ms",  # Malay
            "he",  # Hebrew
            "el",  # Greek
            "cs",  # Czech
            "hu",  # Hungarian
            "ro",  # Romanian
            "uk",  # Ukrainian
        }
    )

    # ISO 639-1 pattern: exactly 2 lowercase letters
    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z]{2}$")

    # Inline rule code to avoid cross-context dependency on LibraryRuleCodes
    _RULE_CODE: ClassVar[str] = "SHARED.LANGUAGE.INVALID_CODE"

    @model_validator(mode="before")
    @classmethod
    def validate_code(cls, value: str) -> str:
        """Validate and normalize the language code.

        Args:
            value: The raw language code.

        Returns:
            The lowercase language code.

        Raises:
            ValueError: If code is not a valid ISO 639-1 format.
        """
        if not isinstance(value, str):
            raise ValueError("Language code must be a string")

        value = value.strip().lower()

        if not cls._PATTERN.match(value):
            examples = ", ".join(sorted(cls.COMMON_CODES)[:5])
            raise ValueError(
                f"Invalid ISO 639-1 language code: '{value}'. "
                f"Must be exactly 2 lowercase letters (e.g. {examples}) "
                f"[{cls._RULE_CODE}]"
            )

        return value

    @classmethod
    def english(cls) -> "LanguageCode":
        """Factory for English language code."""
        return cls("en")

    @classmethod
    def portuguese(cls) -> "LanguageCode":
        """Factory for Portuguese language code."""
        return cls("pt")

    @classmethod
    def japanese(cls) -> "LanguageCode":
        """Factory for Japanese language code."""
        return cls("ja")


__all__ = ["LanguageCode"]
