"""CastMember value object — actor entry on a Movie's cast list."""

from src.building_blocks.domain import CompoundValueObject


class CastMember(CompoundValueObject):
    """A cast entry for a Movie.

    Holds the actor's name, the URL of their TMDB profile photo (when
    available), and the character they played. Replaces the previous
    plain-string cast list so the detail-page UI can render avatars
    and roles instead of just names.

    Attributes:
        name: Actor's display name (always present).
        profile_path: Full URL to the TMDB profile image. ``None`` when
            TMDB doesn't have a photo for this person — the UI falls
            back to an initials avatar.
        role: Character name played by the actor (e.g. "Cobb",
            "Detective Mills"). ``None`` when the source didn't
            provide one.

    Example:
        >>> CastMember(
        ...     name="Leonardo DiCaprio",
        ...     profile_path="https://image.tmdb.org/t/p/original/abc.jpg",
        ...     role="Cobb",
        ... )
    """

    name: str
    profile_path: str | None = None
    role: str | None = None


__all__ = ["CastMember"]
