"""GetPersonBioUseCase - fetch biographical metadata for a TMDB person."""

from dataclasses import dataclass

from src.modules.metadata.application.ports.metadata_provider_port import MetadataProvider


@dataclass(frozen=True)
class GetPersonBioInput:
    """Input for ``GetPersonBioUseCase``.

    Attributes:
        tmdb_id: TMDB person id captured during movie enrichment.
            Provided by the frontend from ``CastMember.tmdb_id``;
            invalid / unknown ids return ``None`` from the use case.
        lang: BCP-47 language tag (e.g. ``"pt-BR"``, ``"en-US"``)
            forwarded to the metadata provider for localized
            biography. The provider falls back to English when the
            requested language has no bio text — see
            ``MetadataProvider.get_person``.
    """

    tmdb_id: int
    lang: str = "en-US"


@dataclass(frozen=True)
class PersonBioOutput:
    """API-shaped representation of a TMDB person's biographical metadata.

    Strict subset of the ``PersonMetadata`` port DTO — only the
    fields the actor page renders today. Adding a field is additive
    everywhere (port → use case → API → frontend type).

    Attributes:
        tmdb_id: TMDB person id (echoed back so the frontend can
            cache by id).
        name: Display name.
        biography: Long-form bio (may be empty when TMDB has none).
        birthday: ISO date or ``None``.
        deathday: ISO date or ``None``.
        place_of_birth: Free-form string or ``None``.
        known_for_department: Primary department on TMDB (e.g.
            ``"Acting"``), or ``None``.
        profile_path: Full URL to profile photo, or ``None``.
    """

    tmdb_id: int
    name: str
    biography: str
    birthday: str | None
    deathday: str | None
    place_of_birth: str | None
    known_for_department: str | None
    profile_path: str | None


class GetPersonBioUseCase:
    """Fetch biographical metadata for a person by TMDB id.

    Thin adapter over ``MetadataProvider.get_person``. The actor
    page calls this on mount with the ``tmdb_id`` forwarded by the
    cast card; absent / unknown ids degrade to ``None`` and the page
    keeps a name-only header.
    """

    def __init__(self, metadata_provider: MetadataProvider) -> None:
        self._metadata_provider = metadata_provider

    async def execute(self, input_dto: GetPersonBioInput) -> PersonBioOutput | None:
        """Execute the use case.

        Args:
            input_dto: ``tmdb_id`` of the person to fetch.

        Returns:
            ``PersonBioOutput`` when the provider returns metadata,
            ``None`` when the provider has no record (404, network
            error, etc.) — caller renders a graceful fallback.
        """
        metadata = await self._metadata_provider.get_person(
            input_dto.tmdb_id,
            language=input_dto.lang,
        )
        if metadata is None:
            return None
        return PersonBioOutput(
            tmdb_id=metadata.tmdb_id,
            name=metadata.name,
            biography=metadata.biography,
            birthday=metadata.birthday,
            deathday=metadata.deathday,
            place_of_birth=metadata.place_of_birth,
            known_for_department=metadata.known_for_department,
            profile_path=metadata.profile_path,
        )


__all__ = ["GetPersonBioInput", "GetPersonBioUseCase", "PersonBioOutput"]
