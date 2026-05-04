"""FastAPI dependency that resolves the caller's ``profile_id``.

Thin wrapper around the centralised
``identity.presentation.dependencies.make_resolve_profile_id``
factory, parameterised with the watch-progress-specific transitional
setting and 401 message. See the factory's docstring for resolution
semantics.
"""

from src.modules.identity.presentation.dependencies import make_resolve_profile_id

resolve_profile_id = make_resolve_profile_id(
    setting_attr="watch_progress_default_profile_id",
    missing_message="Authentication required to access watch progress",
)


__all__ = ["resolve_profile_id"]
