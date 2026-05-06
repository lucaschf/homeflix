"""Rule codes for Collections bounded context validation errors."""


class CollectionRuleCodes:
    """Message codes for collection validation errors.

    These codes are used for i18n translation of error messages.
    """

    # List name validation
    LIST_NAME_EMPTY = "COLLECTION.LIST_NAME.EMPTY"
    LIST_NAME_TOO_LONG = "COLLECTION.LIST_NAME.TOO_LONG"

    # List limits
    CUSTOM_LIST_ITEM_LIMIT_EXCEEDED = "COLLECTION.CUSTOM_LIST.ITEM_LIMIT_EXCEEDED"
