"""Media module bootstrap (ADR-012).

Registers cross-cutting wiring that the BC owns but that needs to be in
place before route or exception handlers fire. Today this only registers
the BC's error-code → HTTP-status mapping.

Called once from the application composition root in ``src/main.py``.
"""


def setup() -> None:
    """Register media-specific HTTP status mappings.

    Imports are deferred inside the function so that importing this
    module is side-effect-free — the registration only happens when the
    composition root chooses to invoke it.
    """
    from src.building_blocks.presentation.error_mapping import register_http_statuses
    from src.modules.media.presentation.error_mapping import MEDIA_HTTP_STATUSES

    register_http_statuses(MEDIA_HTTP_STATUSES)


__all__ = ["setup"]
