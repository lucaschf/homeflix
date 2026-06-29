"""FastAPI dependency that resolves the caller's ``profile_id``.

Re-exports identity's published cross-BC presentation contract
(``identity.presentation.public``).
The per-BC wrapper file still exists so route imports stay
local (``from .dependencies import resolve_profile_id``) — if a
future feature needs a watch-progress-specific override (rate
limit, kids-mode gating, etc.) it can wrap here without touching
every route file.
"""

from src.modules.identity.presentation.public import resolve_profile_id

__all__ = ["resolve_profile_id"]
