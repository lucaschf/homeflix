"""Tests for the error_mapping registry (ADR-012)."""

from collections.abc import Iterator

import pytest

from src.building_blocks.presentation import error_mapping


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Snapshot/restore the registry so mutations don't leak across tests.

    Uses ``error_mapping.isolated_registry()`` so the test depends only
    on the public test-isolation primitive, not on the private
    ``_REGISTRY`` dict. The snapshot includes ``GENERIC_HTTP_STATUSES``
    (auto-registered at import) so generic codes are intact between tests.
    """
    with error_mapping.isolated_registry():
        yield


def _all_subclasses(cls: type) -> set[type]:
    """Return every (transitive) subclass of ``cls``."""
    seen: set[type] = set()
    stack = [cls]
    while stack:
        node = stack.pop()
        for sub in node.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return seen


@pytest.mark.unit
class TestRegisterHttpStatuses:
    """``register_http_statuses`` updates the registry idempotently."""

    def test_should_register_a_new_code(self) -> None:
        error_mapping.register_http_statuses({"NEW_CODE": 418})

        assert error_mapping.resolve_http_status("NEW_CODE") == 418

    def test_should_be_idempotent_when_value_matches(self) -> None:
        error_mapping.register_http_statuses({"NEW_CODE": 418})
        error_mapping.register_http_statuses({"NEW_CODE": 418})

        assert error_mapping.resolve_http_status("NEW_CODE") == 418

    def test_should_raise_when_code_already_registered_with_different_value(
        self,
    ) -> None:
        error_mapping.register_http_statuses({"NEW_CODE": 418})

        with pytest.raises(ValueError, match="Conflicting http_status"):
            error_mapping.register_http_statuses({"NEW_CODE": 451})

    def test_should_register_batch_of_codes(self) -> None:
        error_mapping.register_http_statuses({"CODE_A": 418, "CODE_B": 451})

        assert error_mapping.resolve_http_status("CODE_A") == 418
        assert error_mapping.resolve_http_status("CODE_B") == 451

    def test_should_apply_batch_atomically_on_conflict(self) -> None:
        """A conflict in any entry rolls the whole batch back."""
        error_mapping.register_http_statuses({"EXISTING": 418})

        with pytest.raises(ValueError, match="Conflicting"):
            error_mapping.register_http_statuses({"BRAND_NEW": 451, "EXISTING": 500})

        # All-or-nothing: the offending entry raises, and no entry from
        # the batch is applied. BRAND_NEW must NOT land regardless of
        # the dict iteration order.
        assert error_mapping.resolve_http_status("EXISTING") == 418
        assert error_mapping.resolve_http_status("BRAND_NEW", default=-1) == -1

    def test_should_apply_batch_atomically_on_invalid_status(self) -> None:
        """An out-of-range status in any entry rolls the whole batch back."""
        with pytest.raises(ValueError, match=r"\[100, 599\]"):
            error_mapping.register_http_statuses({"VALID": 418, "BAD": 999})

        # Neither entry should land if any one is invalid.
        assert error_mapping.resolve_http_status("VALID", default=-1) == -1
        assert error_mapping.resolve_http_status("BAD", default=-1) == -1

    @pytest.mark.parametrize("invalid_status", [-1, 0, 99, 600, 1000])
    def test_should_raise_when_status_is_out_of_range(
        self,
        invalid_status: int,
    ) -> None:
        with pytest.raises(ValueError, match=r"\[100, 599\]"):
            error_mapping.register_http_statuses({"BAD_CODE": invalid_status})

    @pytest.mark.parametrize("valid_status", [100, 200, 404, 500, 599])
    def test_should_accept_statuses_at_range_boundaries(
        self,
        valid_status: int,
    ) -> None:
        error_mapping.register_http_statuses({"BOUNDARY_CODE": valid_status})

        assert error_mapping.resolve_http_status("BOUNDARY_CODE") == valid_status


@pytest.mark.unit
class TestResolveHttpStatus:
    """``resolve_http_status`` returns mapped values or the supplied default."""

    def test_should_return_default_for_unknown_code(self) -> None:
        assert error_mapping.resolve_http_status("UNKNOWN_CODE") == 500

    def test_should_accept_custom_default(self) -> None:
        assert error_mapping.resolve_http_status("UNKNOWN_CODE", default=-1) == -1


@pytest.mark.unit
class TestResolveErrorType:
    """``resolve_error_type`` maps HTTP status to v3 error envelope ``type``."""

    def test_should_map_known_statuses(self) -> None:
        assert error_mapping.resolve_error_type(404) == "not_found_error"
        assert error_mapping.resolve_error_type(422) == "validation_error"
        assert error_mapping.resolve_error_type(503) == "service_unavailable_error"

    def test_should_fall_back_to_api_error_for_unmapped_status(self) -> None:
        assert error_mapping.resolve_error_type(999) == "api_error"


@pytest.mark.unit
class TestIsolatedRegistry:
    """``isolated_registry`` snapshots and restores the registry."""

    def test_should_restore_registry_after_context_exits(self) -> None:
        with error_mapping.isolated_registry():
            error_mapping.register_http_statuses({"SCOPED": 418})
            assert error_mapping.resolve_http_status("SCOPED") == 418

        assert error_mapping.resolve_http_status("SCOPED", default=-1) == -1

    def test_should_restore_registry_when_block_raises(self) -> None:
        try:
            with error_mapping.isolated_registry():
                error_mapping.register_http_statuses({"SCOPED": 418})
                raise RuntimeError("simulated failure inside the block")
        except RuntimeError:
            pass

        assert error_mapping.resolve_http_status("SCOPED", default=-1) == -1

    def test_should_preserve_pre_existing_registrations(self) -> None:
        # The autouse fixture has already taken a snapshot that includes
        # GENERIC_HTTP_STATUSES; entering another context-manager scope
        # must not lose those entries on exit.
        with error_mapping.isolated_registry():
            error_mapping.register_http_statuses({"SCOPED": 418})

        assert error_mapping.resolve_http_status("RESOURCE_NOT_FOUND") == 404


@pytest.mark.unit
class TestGenericAutoRegistration:
    """``GENERIC_HTTP_STATUSES`` is registered at import time."""

    def test_should_resolve_resource_not_found(self) -> None:
        assert error_mapping.resolve_http_status("RESOURCE_NOT_FOUND") == 404

    def test_should_resolve_gateway_timeout(self) -> None:
        assert error_mapping.resolve_http_status("GATEWAY_TIMEOUT") == 504

    def test_should_resolve_data_integrity_error(self) -> None:
        assert error_mapping.resolve_http_status("DATA_INTEGRITY_ERROR") == 409


@pytest.mark.unit
class TestRegistryCoverage:
    """Every concrete ``CoreException`` subclass has an explicit registry entry.

    The handler resolves HTTP status via the registry alone (ADR-012);
    a code without a registered status silently falls back to 500. This
    test enumerates every shipped subclass and asserts each one is
    registered, so adding a new exception without updating the BC's
    ``error_mapping.py`` fails CI immediately rather than in production.
    """

    def test_every_core_exception_subclass_has_registry_entry(self) -> None:
        # Force-import error modules so their subclasses are visible
        # via ``CoreException.__subclasses__()``.
        import src.building_blocks.application.errors
        import src.building_blocks.domain.errors
        import src.building_blocks.infrastructure.errors
        import src.modules.identity.domain.errors  # noqa: F401
        from src.building_blocks.domain.errors import CoreException
        from src.modules.identity import bootstrap as identity_bootstrap

        # Identity is bootstrapped from main.py at app creation; do the
        # same here so the coverage check sees the full registry.
        identity_bootstrap.setup()

        sentinel = -1
        missing: list[tuple[str, str]] = []

        for cls in {CoreException, *_all_subclasses(CoreException)}:
            instance = cls(message="probe")
            registered = error_mapping.resolve_http_status(instance.code, default=sentinel)
            if registered == sentinel:
                missing.append((cls.__name__, instance.code))

        assert (
            not missing
        ), f"Codes without registry entry (would fall to 500 default at runtime): {missing}"
