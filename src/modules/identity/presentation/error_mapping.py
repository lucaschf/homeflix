"""Identity-specific HTTP status mappings (ADR-012).

The identity Bounded Context is the only one with codes that don't fall
under the generic transversal mapping today. ``CANNOT_DELETE_LAST_PROFILE``
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
}


__all__ = ["IDENTITY_HTTP_STATUSES"]
