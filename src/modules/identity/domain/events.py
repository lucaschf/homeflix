"""Domain events for the Identity bounded context.

``UserDeletedEvent`` moved to :mod:`src.shared_kernel.integration_events`
(ADR-009) — it is a cross-BC contract consumed by ``watch_progress`` and
``collections``, so it no longer lives in this module's internals.
"""

__all__: list[str] = []
