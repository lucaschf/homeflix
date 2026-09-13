"""Media application-level exceptions.

Authorization errors raised by the catalog use cases when a title is within
the caller's libraries but outside what the caller's viewing policy allows
on the maturity axis (ADR-035, decision 11). They reuse the shared
application-exception bases from ``building_blocks``; their HTTP statuses
are registered by code in ``modules/media/presentation/error_mapping.py``
(ADR-012). Domain-rule violations keep using
``BusinessRuleViolationException`` with ``MediaRuleCodes``.

Neither error names the title — not in the message, not in the details.
A response that did would turn the detail endpoint into an enumeration
oracle for the very profile the gate protects.
"""

from dataclasses import dataclass

from src.building_blocks.application.errors import ForbiddenOperationException
from src.building_blocks.domain.errors import ExceptionDetail
from src.shared_kernel.value_objects.age_rating import AgeRating


@dataclass
class ContentRestrictedByMaturityError(ForbiddenOperationException):
    """The title is rated above the profile's maturity limit.

    Maps to HTTP 403 — never 401, which the web client reads as an
    expired session. The details carry the two ages so the UI can say
    why, and nothing else.

    Attributes:
        required_age: Minimum age the title requires, in years.
        profile_limit: The profile's maturity limit, in years.

    Example:
        >>> raise ContentRestrictedByMaturityError.for_ages(
        ...     required_age=AgeRating(16),
        ...     profile_limit=AgeRating(12),
        ... )
    """

    code: str = "CONTENT_RESTRICTED_BY_MATURITY"
    message_code: str = "CONTENT_RESTRICTED_BY_MATURITY"
    required_age: int | None = None
    profile_limit: int | None = None

    def __post_init__(self) -> None:
        """Expose both ages as i18n params and as the response details."""
        super().__post_init__()
        self.message_params = {
            "required_age": self.required_age,
            "profile_limit": self.profile_limit,
        }
        if self.required_age is not None and self.profile_limit is not None:
            # Assigned, not appended: ``with_translation`` rebuilds the
            # instance through ``dataclasses.replace``, which re-runs this.
            self.details = [
                ExceptionDetail(
                    code=self.code,
                    message=(
                        f"Requires age {self.required_age}; "
                        f"profile limit is {self.profile_limit}"
                    ),
                    metadata={
                        "required_age": self.required_age,
                        "profile_limit": self.profile_limit,
                    },
                )
            ]

    @classmethod
    def for_ages(
        cls,
        *,
        required_age: AgeRating,
        profile_limit: AgeRating,
    ) -> "ContentRestrictedByMaturityError":
        """Factory for a title rated above the profile's limit.

        Args:
            required_age: Minimum age the title requires.
            profile_limit: The profile's maturity limit.

        Returns:
            ContentRestrictedByMaturityError carrying both ages.
        """
        return cls(
            message="This title is above the profile's maturity limit",
            required_age=required_age.value,
            profile_limit=profile_limit.value,
        )


@dataclass
class ContentRestrictedUnratedError(ForbiddenOperationException):
    """The title has no determinable rating and the profile has a limit below adult.

    Kept apart from :class:`ContentRestrictedByMaturityError` so the UI
    can offer an administrator the shortcut to classify the title
    instead of a dead end. Maps to HTTP 403. There is no required age
    to report — undetermined content resolves to adult
    (``AgeRating.allows``), so only the profile's limit is in the details.

    Attributes:
        profile_limit: The profile's maturity limit, in years.

    Example:
        >>> raise ContentRestrictedUnratedError.for_limit(AgeRating(12))
    """

    code: str = "CONTENT_RESTRICTED_UNRATED"
    message_code: str = "CONTENT_RESTRICTED_UNRATED"
    profile_limit: int | None = None

    def __post_init__(self) -> None:
        """Expose the profile limit as an i18n param and as the response details."""
        super().__post_init__()
        self.message_params = {"profile_limit": self.profile_limit}
        if self.profile_limit is not None:
            # Assigned, not appended — see ContentRestrictedByMaturityError.
            self.details = [
                ExceptionDetail(
                    code=self.code,
                    message=f"Unrated; profile limit is {self.profile_limit}",
                    metadata={"profile_limit": self.profile_limit},
                )
            ]

    @classmethod
    def for_limit(cls, profile_limit: AgeRating) -> "ContentRestrictedUnratedError":
        """Factory for an unrated title under a profile limit below adult.

        Args:
            profile_limit: The profile's maturity limit.

        Returns:
            ContentRestrictedUnratedError carrying the limit.
        """
        return cls(
            message="This title is unrated and the profile has a maturity limit",
            profile_limit=profile_limit.value,
        )


__all__ = [
    "ContentRestrictedByMaturityError",
    "ContentRestrictedUnratedError",
]
