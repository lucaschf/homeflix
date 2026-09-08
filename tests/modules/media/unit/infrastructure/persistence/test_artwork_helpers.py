"""Unit tests for the localized-artwork JSON path builder (ADR-023/ADR-029).

The path is the only piece of JSON knowledge the mirror's localized
write path carries, so its two properties are pinned here: field names
come from ``LocalizedField``, and the locale key is validated — never
rewritten — before it is quoted into the path.
"""

import pytest

from src.modules.media.domain.value_objects.localized_metadata import LocalizedField
from src.modules.media.infrastructure.persistence.repositories._artwork_helpers import (
    localized_artwork_path,
)


class TestLocalizedArtworkPath:
    def test_should_quote_the_locale_and_use_the_field_name(self) -> None:
        path = localized_artwork_path("pt-BR", LocalizedField.POSTER_PATH)

        assert path == '$."pt-BR".poster_path'

    @pytest.mark.parametrize("locale", ["en", "pt-br", "es-419", "zh-Hant-TW"])
    def test_should_accept_language_tag_shaped_keys_verbatim(self, locale: str) -> None:
        assert localized_artwork_path(locale, LocalizedField.LOGO_PATH) == (
            f'$."{locale}".logo_path'
        )

    @pytest.mark.parametrize("locale", ["", "a", "pt.BR", 'pt"BR', "pt BR", "x" * 36])
    def test_should_reject_keys_that_cannot_be_a_json_path_segment(self, locale: str) -> None:
        with pytest.raises(ValueError, match="unsafe locale key"):
            localized_artwork_path(locale, LocalizedField.BACKDROP_PATH)
