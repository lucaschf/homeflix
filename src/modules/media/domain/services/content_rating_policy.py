"""Choosing which jurisdiction's certification a title carries (ADR-035).

A title is usually rated by several boards and they disagree — the same
film is ``R`` in the United States and ``16`` in Brazil. Picking one is a
decision of the household, so it lives here in the domain rather than in
the provider adapter, whose job is to report every rating it saw and
nothing more (ADR-025).

The service is pure and synchronous, and takes the *policy inputs* rather
than the Settings bucket that happens to hold them: the domain does not
know a Settings context exists (ADR-009). The caller reads the
configuration and unpacks it, the way ``AdminQuorum`` takes its derived
facts as parameters.
"""

from collections.abc import Mapping, Sequence

from src.shared_kernel.content_policy import ContentRatingFallback, classify, strictest
from src.shared_kernel.value_objects.certification import Certification


class ContentRatingPolicy:
    """Selects one certification out of a per-country map."""

    @staticmethod
    def select(
        certifications: Mapping[str, str],
        *,
        jurisdictions: Sequence[str],
        fallback: ContentRatingFallback = ContentRatingFallback.STRICTEST_AVAILABLE,
    ) -> Certification | None:
        """Pick the certification the catalog should store for a title.

        Preferred jurisdictions are tried in order and the first that
        rated the title wins — **even when its label yields no age**. A
        board that reviewed a title and returned ``NR`` has said
        something, and falling through to a board further down the list
        would quietly overrule the jurisdiction the household chose.

        Args:
            certifications: Country code (ISO 3166-1 alpha-2) to the
                label that board issued, exactly as the provider
                reported it.
            jurisdictions: Country codes in order of preference.
            fallback: What to do when none of ``jurisdictions`` rated
                this title.

        Returns:
            The chosen certification, or ``None`` when nothing was
            selected — which every consumer resolves to adult.

        Example:
            >>> ContentRatingPolicy.select(
            ...     {"US": "R", "BR": "16"},
            ...     jurisdictions=["BR", "US"],
            ... ).minimum_age.value
            16
        """
        by_country = {
            str(country).strip().upper(): str(label)
            for country, label in certifications.items()
            if str(country).strip() and str(label).strip()
        }
        if not by_country:
            return None

        for country in jurisdictions:
            label = by_country.get(str(country).strip().upper())
            if label is None:
                continue
            chosen = classify(label, country=country)
            if chosen is not None:
                return chosen
            # The board rated this title but wrote something this
            # catalog cannot store as a label. That is not a statement
            # to record, unlike ``NR``, so keep looking down the list
            # instead of leaving the title unrated over one board's
            # wording.

        if fallback is ContentRatingFallback.NONE:
            return None

        # Sorted so the choice is deterministic when two boards tie on
        # the same age — otherwise the stored system would depend on
        # dict ordering from the provider payload.
        candidates = [
            certification
            for certification in (
                classify(label, country=country) for country, label in sorted(by_country.items())
            )
            if certification is not None
        ]
        if not candidates:
            return None

        # Prefer a board whose label yields an age. When none does, keep
        # the first one anyway: a title every board marked ``NR`` is
        # still a title that was reviewed, and the label is what the
        # badge renders. Returning ``None`` here would gate it exactly
        # the same way — undetermined resolves to adult — while silently
        # erasing the rating from the UI, which is the one thing
        # ADR-035 says must not change.
        return strictest(candidates) or candidates[0]


__all__ = ["ContentRatingPolicy"]
