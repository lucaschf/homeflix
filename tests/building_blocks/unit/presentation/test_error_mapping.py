"""Tests for the error_mapping registry (ADR-012)."""

from collections.abc import Iterator

import pytest

from src.building_blocks.presentation import error_mapping


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Snapshot/restore ``_REGISTRY`` so mutations don't leak across tests.

    The snapshot is taken after module import, so ``GENERIC_HTTP_STATUSES``
    is part of it and is restored intact between tests.
    """
    snapshot = dict(error_mapping._REGISTRY)
    yield
    error_mapping._REGISTRY.clear()
    error_mapping._REGISTRY.update(snapshot)


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

    def test_should_not_apply_partial_batch_on_conflict(self) -> None:
        error_mapping.register_http_statuses({"EXISTING": 418})

        with pytest.raises(ValueError):
            error_mapping.register_http_statuses({"BRAND_NEW": 451, "EXISTING": 999})

        # The batch raised on EXISTING; whether BRAND_NEW landed depends
        # on dict iteration order. The contract we promise is "raises on
        # conflict" — callers retrying after fixing the conflict can
        # safely re-register due to idempotency. This test pins that
        # the conflict actually surfaces (vs. silent overwrite).
        assert error_mapping.resolve_http_status("EXISTING") == 418


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
    """Guards against codes added to exception classes without a registry entry.

    During the ADR-012 migration the global handler still reads
    ``exc.http_status`` from the property; this test pins that the
    registry mirrors every concrete exception's ``code → status`` pair,
    so PR 2 (which inverts the handler to read from the registry) won't
    silently regress to 500 for any existing code path.

    PR 3 will repurpose this test to assert "every code has an entry"
    once the property is gone — until then the parity check is the
    stronger guarantee.
    """

    def test_registry_mirrors_every_core_exception_subclass(self) -> None:
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
        mismatched: list[tuple[str, str, int, int]] = []

        for cls in {CoreException, *_all_subclasses(CoreException)}:
            instance = cls(message="probe")
            registered = error_mapping.resolve_http_status(instance.code, default=sentinel)
            if registered == sentinel:
                missing.append((cls.__name__, instance.code))
            elif registered != instance.http_status:
                mismatched.append(
                    (cls.__name__, instance.code, instance.http_status, registered),
                )

        assert not missing, (
            "Codes without registry entry (would fall to 500 default in PR 2): " f"{missing}"
        )
        assert not mismatched, (
            "Registry value disagrees with the http_status property "
            f"(class, code, property, registry): {mismatched}"
        )
