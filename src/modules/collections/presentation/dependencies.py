"""FastAPI dependency that resolves the caller's ``profile_id`` for collections.

Re-exports the canonical strict-mode helper from the identity BC.
The per-BC wrapper file still exists so route imports stay local
(``from .dependencies import resolve_profile_id``) — if a future
feature needs a collections-specific override (e.g. shared lists)
it can wrap here without touching every route file.
"""

from src.modules.identity.presentation.dependencies import resolve_profile_id

__all__ = ["resolve_profile_id"]
