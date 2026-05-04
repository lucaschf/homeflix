"""FastAPI dependency that resolves the caller's ``profile_id`` for collections.

Thin wrapper around the centralised
``identity.presentation.dependencies.make_resolve_profile_id``
factory, parameterised with the collections-specific transitional
setting and 401 message. See the factory's docstring for resolution
semantics.
"""

from src.modules.identity.presentation.dependencies import make_resolve_profile_id

resolve_profile_id = make_resolve_profile_id(
    setting_attr="collections_default_profile_id",
    missing_message="Authentication required to access collections",
)


__all__ = ["resolve_profile_id"]
