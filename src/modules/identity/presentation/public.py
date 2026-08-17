"""Published cross-bounded-context presentation contract for ``identity``.

See ADR-024 (Published Presentation Contracts for Cross-BC Imports) for the
decision and rationale that this module implements.

This module is the **sanctioned, stable surface** that other bounded
contexts' presentation layers may import from ``identity``. Everything
else under ``identity/presentation/`` (``get_current_profile``,
``ProfileContext``, the auth wiring, the UoW-factory resolver) is internal
and must not be imported across BC boundaries.

Why a cross-BC import is allowed here at all (vs. ADR-008 "modules don't
import each other" / ADR-009 "cross-BC reads go through a port + ACL"):

- ADR-009's port+ACL pattern governs **domain/application reads** — a use
  case depending on another BC's data. ``resolve_profile_id`` is neither:
  it is a **FastAPI request-context dependency** that turns the session
  cookie into the caller's ``profile_id`` at the HTTP edge. There is no
  domain port to route an ``Request`` through.
- Per ADR-010/011 ``identity`` owns authentication and profile resolution;
  every authenticated route in every BC needs "who is the caller". That
  makes identity's auth dependency an inherently shared presentation
  primitive, like a shared auth library — not an accidental reach into
  another module's internals.

Consumers import this via their own thin ``presentation/dependencies.py``
shim (so route imports stay local and a BC can wrap for an override),
which in turn imports from here. Keeping the contract in a dedicated
module lets ``identity`` refactor its internal ``dependencies.py`` freely
without rippling into four other bounded contexts.
"""

from src.modules.identity.infrastructure.auth import (
    AuthenticatedUser,
    authenticated_admin,
    authenticated_user,
)
from src.modules.identity.presentation.dependencies import resolve_profile_id

# The route guards are the other half of the published contract: every
# authenticated route in every BC needs "who is the caller" (and "is the
# caller an admin"). They live in ``infrastructure/auth`` because they are
# FastAPI ``Depends`` chains, but they are re-exported here so consumers
# import the sanctioned surface rather than reaching into identity's
# internals — keeping identity free to refactor the auth wiring (ADR-024).
__all__ = [
    "AuthenticatedUser",
    "authenticated_admin",
    "authenticated_user",
    "resolve_profile_id",
]
