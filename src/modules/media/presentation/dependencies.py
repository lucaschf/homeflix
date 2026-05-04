"""FastAPI dependency that resolves the caller's ``profile_id`` for the catalog.

Thin wrapper around the centralised
``identity.presentation.dependencies.make_resolve_profile_id``
factory, parameterised with the media-specific transitional setting
and 401 message. See the factory's docstring for resolution
semantics.
"""

from src.modules.identity.presentation.dependencies import make_resolve_profile_id

resolve_profile_id = make_resolve_profile_id(
    setting_attr="media_default_profile_id",
    missing_message="Authentication required to access the catalog",
)


__all__ = ["resolve_profile_id"]
