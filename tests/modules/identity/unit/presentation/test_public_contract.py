"""The published cross-BC presentation contract for identity."""

import pytest


@pytest.mark.unit
class TestIdentityPublicContract:
    """``identity.presentation.public`` is the sanctioned cross-BC surface."""

    def test_exposes_the_sanctioned_surface(self) -> None:
        from src.modules.identity.presentation import public

        # The published surface is resolve_profile_id + the route guards
        # (ADR-024). Nothing else from identity may be imported cross-BC.
        assert public.__all__ == [
            "AuthenticatedUser",
            "authenticated_admin",
            "authenticated_user",
            "resolve_profile_id",
        ]
        assert callable(public.resolve_profile_id)
        assert callable(public.authenticated_admin)
        assert callable(public.authenticated_user)

    def test_guards_are_the_infrastructure_ones(self) -> None:
        from src.modules.identity.infrastructure import auth
        from src.modules.identity.presentation import public

        # Re-exports the real guards — no fork.
        assert public.authenticated_admin is auth.authenticated_admin
        assert public.authenticated_user is auth.authenticated_user
        assert public.AuthenticatedUser is auth.AuthenticatedUser

    def test_resolve_profile_id_is_the_canonical_dependency(self) -> None:
        from src.modules.identity.presentation import dependencies, public

        # The contract re-exports the one real implementation — no fork.
        assert public.resolve_profile_id is dependencies.resolve_profile_id

    def test_consumer_shims_re_export_the_same_object(self) -> None:
        from src.modules.collections.presentation import dependencies as collections_deps
        from src.modules.identity.presentation import public
        from src.modules.media.presentation import dependencies as media_deps
        from src.modules.preferences.presentation import dependencies as preferences_deps
        from src.modules.watch_progress.presentation import dependencies as progress_deps

        for shim in (collections_deps, media_deps, preferences_deps, progress_deps):
            assert shim.resolve_profile_id is public.resolve_profile_id
