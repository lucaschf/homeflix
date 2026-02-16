"""Rule codes for Library bounded context validation errors."""


class LibraryRuleCodes:
    """Message codes for library validation errors.

    These codes are used for i18n translation of error messages.
    """

    # Library name validation
    LIBRARY_NAME_EMPTY = "LIBRARY.NAME.EMPTY"
    LIBRARY_NAME_TOO_LONG = "LIBRARY.NAME.TOO_LONG"

    # Language code validation
    INVALID_LANGUAGE_CODE = "LIBRARY.LANGUAGE.INVALID_CODE"

    # Path validation
    LIBRARY_NO_PATHS = "LIBRARY.PATHS.EMPTY"
    LIBRARY_DUPLICATE_PATH = "LIBRARY.PATHS.DUPLICATE"

    # Metadata provider validation
    DUPLICATE_PROVIDER_PRIORITY = "LIBRARY.PROVIDER.DUPLICATE_PRIORITY"
