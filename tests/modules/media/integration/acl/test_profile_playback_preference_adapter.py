"""Integration tests for the Media ProfilePlaybackPreferenceAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.infrastructure.acl.profile_playback_preference_adapter import (
    ProfilePlaybackPreferenceAdapter,
)
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)
from src.modules.preferences.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyPreferencesUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _make_adapter(
    session_factory: async_sessionmaker[AsyncSession],
) -> ProfilePlaybackPreferenceAdapter:
    return ProfilePlaybackPreferenceAdapter(SqlAlchemyPreferencesUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestProfilePlaybackPreferenceAdapter:
    """The adapter reads audio_lang and bridges the IETF tag to a LanguageCode."""

    async def test_returns_base_language_code_of_configured_audio_lang(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        repo = SQLAlchemyPreferencesRepository(db_session)
        await repo.save(
            PlaybackPreferences.default_for(_PROFILE_ID).apply_updates(audio_lang="pt-BR"),
        )
        await db_session.commit()

        adapter = _make_adapter(session_factory)
        result = await adapter.for_profile(str(_PROFILE_ID))

        # IETF "pt-BR" bridges to the strict ISO 639-1 base "pt".
        assert result.audio_language == LanguageCode("pt")

    async def test_defaults_when_no_preferences_row(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # First access: no row → factory default (pt-BR) → base "pt", so the
        # server resolves the same default the client would apply.
        adapter = _make_adapter(session_factory)

        result = await adapter.for_profile(str(_PROFILE_ID))

        assert result.audio_language == LanguageCode("pt")

    async def test_unbridgeable_tag_yields_no_audio_language(
        self,
        db_session: AsyncSession,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # A 3-letter primary subtag is a valid IETF tag but not a strict
        # ISO 639-1 code, so it can't bridge to a LanguageCode → the adapter
        # applies no audio preference (None) rather than raising.
        repo = SQLAlchemyPreferencesRepository(db_session)
        await repo.save(
            PlaybackPreferences.default_for(_PROFILE_ID).apply_updates(audio_lang="fil"),
        )
        await db_session.commit()

        adapter = _make_adapter(session_factory)
        result = await adapter.for_profile(str(_PROFILE_ID))

        assert result.audio_language is None
