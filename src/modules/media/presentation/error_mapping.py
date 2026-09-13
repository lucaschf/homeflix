"""Media-specific HTTP status mappings (ADR-012).

Both maturity-gate codes restate the 403 their parent
``ForbiddenOperationException`` already resolves to, because the registry
is flat and indexed by code, not by exception class. 403 and not 401 is
load-bearing (ADR-035, decision 11): the web client treats an unexpected
401 as an expired session and signs the viewer out.
"""

MEDIA_HTTP_STATUSES: dict[str, int] = {
    "CONTENT_RESTRICTED_BY_MATURITY": 403,
    "CONTENT_RESTRICTED_UNRATED": 403,
}


__all__ = ["MEDIA_HTTP_STATUSES"]
