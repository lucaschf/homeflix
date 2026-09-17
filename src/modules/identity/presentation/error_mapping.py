"""Identity-specific HTTP status mappings (ADR-012).

The identity Bounded Context has codes that don't fall under the generic
transversal mapping. ``CANNOT_DELETE_LAST_PROFILE``
and ``NO_ACTIVE_PROFILE`` map to 409 (the parent ``ApplicationException``
defaults to 400, so the override is meaningful); the remaining entries
restate inherited statuses explicitly because the registry is flat and
indexed by code, not by exception class.
"""

IDENTITY_HTTP_STATUSES: dict[str, int] = {
    "PROFILE_NOT_FOUND": 404,
    "PROFILE_OWNERSHIP_VIOLATION": 403,
    "NO_ACTIVE_SESSION": 401,
    "CANNOT_DELETE_LAST_PROFILE": 409,
    "NO_ACTIVE_PROFILE": 409,
    "USER_NOT_FOUND": 404,
    "USER_EMAIL_ALREADY_EXISTS": 409,
    "USER_CANNOT_DELETE_SELF": 409,
    "USER_CANNOT_DEMOTE_LAST_ADMIN": 409,
    "ACCOUNT_PASSWORD_INVALID": 403,
    # Avatar upload: the status says which byte check refused the file.
    # 413 and 415 are not defaults of any base class, so both entries are
    # load-bearing rather than restatements.
    "AVATAR_TOO_LARGE": 413,
    "AVATAR_INVALID_IMAGE": 415,
    # Parental controls (ADR-035): 403 or 409, never 401 — the web client
    # reads any 401 as an expired session.
    "PARENTAL_PIN_REQUIRED": 403,
    "PARENTAL_PIN_INVALID": 403,
    "PARENTAL_PIN_LOCKED": 403,
    "PARENTAL_PIN_NOT_CONFIGURED": 409,
    "PARENTAL_PIN_IN_USE": 409,
}


__all__ = ["IDENTITY_HTTP_STATUSES"]
