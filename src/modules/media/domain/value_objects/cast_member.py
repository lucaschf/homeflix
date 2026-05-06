"""CastMember value object — actor entry on a Movie's cast list."""

from src.building_blocks.domain import CompoundValueObject


class CastMember(CompoundValueObject):
    """A cast entry for a Movie.

    Holds the actor's name, the URL of their TMDB profile photo (when
    available), the character they played, and the TMDB person id
    (when the row was enriched against TMDB). The id unblocks the
    "browse by actor" page from joining on bio / birth date / known
    department without ambiguity — name-only matching collides for
    homonyms.

    Attributes:
        name: Actor's display name (always present).
        profile_path: Full URL to the TMDB profile image. ``None`` when
            TMDB doesn't have a photo for this person — the UI falls
            back to an initials avatar.
        role: Character name played by the actor (e.g. "Cobb",
            "Detective Mills"). ``None`` when the source didn't
            provide one.
        tmdb_id: TMDB person id. ``None`` for rows enriched before the
            id was captured — those degrade to a name-only flow on
            the actor page (no bio / birth date) and pick up the id
            on the next re-enrichment.

    Example:
        >>> CastMember(
        ...     name="Leonardo DiCaprio",
        ...     profile_path="https://image.tmdb.org/t/p/original/abc.jpg",
        ...     role="Cobb",
        ...     tmdb_id=6193,
        ... )
    """

    name: str
    profile_path: str | None = None
    role: str | None = None
    tmdb_id: int | None = None


__all__ = ["CastMember"]
