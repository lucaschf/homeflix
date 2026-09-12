"""Which jurisdiction's certification the catalog trusts (ADR-035)."""

from pydantic import Field, field_validator

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.content_policy import ContentRatingFallback


class ContentRatingConfig(CompoundValueObject):
    """Jurisdiction preference for normalizing certifications.

    A title is usually rated by several boards, and they disagree: the
    same film is ``R`` (17) in the United States and ``16`` in Brazil.
    Picking one is a policy of the household, not a fact about the
    title, so it belongs in a settings bucket rather than hardcoded in
    the provider adapter — which is where it used to live, inferred
    from ``supported_locales`` as a proxy (ADR-035, decision 10).

    Attributes:
        jurisdictions: ISO 3166-1 alpha-2 country codes, most trusted
            first. The first one that rated a title wins. Empty means
            no preference, so every title takes the fallback path.
        fallback: What happens when none of ``jurisdictions`` rated the
            title.

    Example:
        >>> cfg = ContentRatingConfig()
        >>> cfg.jurisdictions
        ['BR', 'US']
        >>> strict = cfg.with_updates(jurisdictions=["BR"])
    """

    jurisdictions: list[str] = Field(default_factory=lambda: ["BR", "US"])
    fallback: ContentRatingFallback = ContentRatingFallback.STRICTEST_AVAILABLE

    @field_validator("jurisdictions", mode="before")
    @classmethod
    def normalize_jurisdictions(cls, v: list[str] | None) -> list[str]:
        """Upper-case, trim, drop blanks and duplicates, preserving order.

        Order is the whole meaning of the field, so de-duplication keeps
        the first occurrence rather than sorting.
        """
        if not v:
            return []

        seen: list[str] = []
        for raw in v:
            code = str(raw).strip().upper()
            if code and code not in seen:
                seen.append(code)
        return seen

    @field_validator("jurisdictions")
    @classmethod
    def validate_country_codes(cls, v: list[str]) -> list[str]:
        """Reject anything that is not a 2-letter country code."""
        for code in v:
            if len(code) != 2 or not code.isalpha():
                raise ValueError(
                    f"Jurisdiction must be a 2-letter ISO 3166-1 country code, got {code!r}"
                )
        return v


__all__ = ["ContentRatingConfig"]
