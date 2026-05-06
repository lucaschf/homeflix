"""Decentralized error code → HTTP status registry (ADR-012).

Holds the source of truth for `error_code → http_status` mapping. Each
Bounded Context with module-specific codes registers its own mapping at
bootstrap; transversal codes (`RESOURCE_NOT_FOUND`, `GATEWAY_TIMEOUT`,
etc.) live in ``GENERIC_HTTP_STATUSES`` and auto-register on import.

This is the foundation step of the migration in ADR-012. During this PR
the global handler still reads ``exc.http_status`` from the exception
property; a coverage test guards parity between the property and this
registry. Subsequent PRs invert the handler and remove the property.
"""

from collections.abc import Iterator
from contextlib import contextmanager

_REGISTRY: dict[str, int] = {}

_STATUS_TO_ERROR_TYPE: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    405: "invalid_request_error",
    409: "conflict_error",
    413: "request_too_large_error",
    415: "invalid_request_error",
    422: "validation_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "bad_gateway_error",
    503: "service_unavailable_error",
    504: "gateway_timeout_error",
}

GENERIC_HTTP_STATUSES: dict[str, int] = {
    # Core
    "CORE_ERROR": 500,
    # Domain
    "DOMAIN_ERROR": 422,
    "DOMAIN_VALIDATION_ERROR": 422,
    "BUSINESS_RULE_VIOLATION": 422,
    "DOMAIN_NOT_FOUND": 404,
    "DOMAIN_CONFLICT": 409,
    # Application
    "APPLICATION_ERROR": 400,
    "USE_CASE_VALIDATION_ERROR": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "RESOURCE_NOT_FOUND": 404,
    # Infrastructure
    "INFRASTRUCTURE_ERROR": 500,
    "GATEWAY_ERROR": 500,
    "GATEWAY_TIMEOUT": 504,
    "GATEWAY_UNAVAILABLE": 503,
    "GATEWAY_RATE_LIMIT": 429,
    "GATEWAY_BAD_RESPONSE": 502,
    "CIRCUIT_OPEN": 503,
    "REPOSITORY_ERROR": 500,
    "DATABASE_CONNECTION_ERROR": 503,
    "DATA_INTEGRITY_ERROR": 409,
    "FILESYSTEM_ERROR": 500,
    "FILE_NOT_FOUND": 404,
    "FILE_ACCESS_ERROR": 500,
}


def register_http_statuses(mapping: dict[str, int]) -> None:
    """Register a batch of ``error_code → http_status`` entries.

    Transactional: the batch is validated in full before any entry is
    written. If any status is out of range or any code conflicts with
    an existing different value, no entry from the batch is applied —
    callers can fix the offending entry and retry without worrying that
    earlier entries already landed.

    Idempotent for equal values (registering the same pair repeatedly is
    a no-op). Conflicts — same code, different status — raise instead
    of silently overwriting, since silent wins would mask bootstrap-order
    bugs and cross-BC code collisions.

    Args:
        mapping: Dict of error code → HTTP status code. Each status must
            be a valid HTTP status code in the inclusive range [100, 599].

    Raises:
        ValueError: If any status is outside [100, 599], or if a code is
            already registered with a different status. The exception
            message identifies the offending entry so the caller can
            decide which BC owns the code.

    Example:
        >>> register_http_statuses({"PROFILE_NOT_FOUND": 404})
    """
    # Phase 1 — validate every entry. No mutation until the batch is clean.
    for code, status in mapping.items():
        if not 100 <= status <= 599:
            raise ValueError(f"HTTP status for code {code!r} must be in [100, 599], got {status}")
        existing = _REGISTRY.get(code)
        if existing is not None and existing != status:
            raise ValueError(
                f"Conflicting http_status registration for code {code!r}: "
                f"already registered as {existing}, new value {status}"
            )
    # Phase 2 — commit. All entries pass validation so this is atomic
    # from the caller's perspective.
    _REGISTRY.update(mapping)


@contextmanager
def isolated_registry() -> Iterator[None]:
    """Snapshot the registry on entry, restore the snapshot on exit.

    Test-isolation primitive that lets a block mutate the registry
    without leaking changes to subsequent code. Equivalent to a
    save/restore around any number of ``register_http_statuses`` calls.

    Example:
        >>> with isolated_registry():
        ...     register_http_statuses({"TEMP_CODE": 418})
        ...     assert resolve_http_status("TEMP_CODE") == 418
        >>> resolve_http_status("TEMP_CODE", default=-1)  # restored
        -1
    """
    snapshot = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(snapshot)


def resolve_http_status(code: str, default: int = 500) -> int:
    """Resolve an error code to its HTTP status.

    Returns ``default`` if the code is not registered. Callers that want
    to detect unregistered codes (e.g. coverage tests) should pass a
    sentinel value distinguishable from a valid status.

    Args:
        code: Error code (matches ``CoreException.code``).
        default: Status returned for unknown codes. Defaults to 500.

    Returns:
        HTTP status code.
    """
    return _REGISTRY.get(code, default)


def resolve_error_type(http_status: int) -> str:
    """Resolve an HTTP status to the v3 error envelope ``type`` field.

    Args:
        http_status: HTTP status code.

    Returns:
        Error type string (e.g. ``"validation_error"``, ``"not_found_error"``).
        Falls back to ``"api_error"`` for unmapped statuses.
    """
    return _STATUS_TO_ERROR_TYPE.get(http_status, "api_error")


# Auto-register transversal building_blocks codes at import time so
# the registry is usable as soon as anyone imports this module.
register_http_statuses(GENERIC_HTTP_STATUSES)


__all__ = [
    "GENERIC_HTTP_STATUSES",
    "isolated_registry",
    "register_http_statuses",
    "resolve_error_type",
    "resolve_http_status",
]
