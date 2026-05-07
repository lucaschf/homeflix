"""Identity module bootstrap (ADR-012).

Registers cross-cutting wiring that the BC owns but that needs to be in
place before route or exception handlers fire. Today this only registers
the BC's error-code → HTTP-status mapping; future bootstrap-time concerns
(e.g. translation catalog hooks) would also go here.

Called once from the application composition root in ``src/main.py``.
"""


def setup() -> None:
    """Register identity-specific HTTP status mappings.

    Imports are deferred inside the function so that importing this
    module is side-effect-free — the registration only happens when the
    composition root chooses to invoke it.
    """
    from src.building_blocks.presentation.error_mapping import register_http_statuses
    from src.modules.identity.presentation.error_mapping import IDENTITY_HTTP_STATUSES

    register_http_statuses(IDENTITY_HTTP_STATUSES)


__all__ = ["setup"]
