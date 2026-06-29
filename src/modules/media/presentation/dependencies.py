"""FastAPI dependency that resolves the caller's ``profile_id`` for the catalog.

Re-exports identity's published cross-BC presentation contract
(``identity.presentation.public``).
The per-BC wrapper file still exists so route imports stay local
(``from .dependencies import resolve_profile_id``) — future
catalog-specific overrides (e.g. parental controls, kids-mode
filtering) plug in here without touching every route file.
"""

from src.modules.identity.presentation.public import resolve_profile_id

__all__ = ["resolve_profile_id"]
