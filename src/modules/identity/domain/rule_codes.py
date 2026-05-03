"""Rule codes for Identity bounded context validation errors.

These codes are used for i18n translation of error messages.
"""


class IdentityRuleCodes:
    """Message codes for identity validation errors."""

    # Email validation
    EMAIL_EMPTY = "IDENTITY.EMAIL.EMPTY"
    EMAIL_INVALID_FORMAT = "IDENTITY.EMAIL.INVALID_FORMAT"
    EMAIL_TOO_LONG = "IDENTITY.EMAIL.TOO_LONG"

    # Profile name validation
    PROFILE_NAME_EMPTY = "IDENTITY.PROFILE.NAME.EMPTY"
    PROFILE_NAME_TOO_LONG = "IDENTITY.PROFILE.NAME.TOO_LONG"

    # Profile ownership / lifecycle
    PROFILE_OWNERSHIP_VIOLATION = "IDENTITY.PROFILE.OWNERSHIP_VIOLATION"
    PROFILE_NOT_FOUND = "IDENTITY.PROFILE.NOT_FOUND"
    CANNOT_DELETE_LAST_PROFILE = "IDENTITY.PROFILE.CANNOT_DELETE_LAST"

    # Session / authentication
    NO_ACTIVE_SESSION = "IDENTITY.SESSION.NONE"
    NO_ACTIVE_PROFILE = "IDENTITY.SESSION.NO_PROFILE_SELECTED"
