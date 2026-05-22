"""Settings bounded context.

Persists operational tunables (scheduler, thumbnail backfill, intro
detection, streaming, avatar) in the ``app_settings`` table and exposes
them via :class:`RuntimeSettings`. See ADR-013 for the design.
"""
