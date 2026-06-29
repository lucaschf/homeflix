"""The published cross-BC presentation contract for identity."""

import pytest


@pytest.mark.unit
class TestIdentityPublicContract:
    """``identity.presentation.public`` is the sanctioned cross-BC surface."""

    def test_exposes_resolve_profile_id(self) -> None:
        from src.modules.identity.presentation import public

        assert public.__all__ == ["resolve_profile_id"]
        assert callable(public.resolve_profile_id)

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
