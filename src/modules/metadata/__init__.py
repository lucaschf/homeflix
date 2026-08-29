"""Metadata / Enrichment provider bounded context (ADR-032).

Supporting subdomain that owns the external metadata provider gateway
(TMDB) plus artwork mirroring (storage + download) and the pure
provider lookups. It publishes the ``MetadataProvider`` port and its
DTOs as a contract the Media catalog consumes for enrichment; the
enrichment write-backs themselves stay in Media.
"""
