"""Bootstrap an admin user + default profile for the identity BC.

Run from the project root with the virtualenv active:

    poetry run python scripts/identity_create_admin.py

The script prompts for email, password (twice for confirmation), and
the default profile's display name, then:

1. Initialises the application container (engine + session factory).
2. Hashes the password using ``pwdlib`` — the same hasher FastAPI
   Users uses at login, so subsequent ``POST /auth/cookie/login``
   calls verify against the same bytes.
3. Creates a ``User`` aggregate with ``role=ADMIN``,
   ``is_superuser=True``, ``is_verified=True`` and persists it via
   ``UserRepository``.
4. Creates a default ``Profile`` for the new admin via the
   ``CreateProfileUseCase`` and grants it access to every library
   currently registered, so the operator can use the catalog
   immediately. The domain default for ``allowed_library_ids`` is
   the empty list (deny-all) — that's the right default for new
   household members added via the UI later, but the bootstrap
   account is the operator's admin and would otherwise see an
   empty catalog after first login. The grant snapshots the
   current libraries; libraries added afterward need an explicit
   grant via ``PUT /api/v1/profiles/{id}``.

Bootstrap path lives in ``scripts/`` rather than as a public route
because PR 1 deliberately does not expose ``/auth/register`` —
self-service registration UX is undefined and admin-creation is a
once-per-deployment action. See ADR-010 / ADR-011 for the framing.
"""

from __future__ import annotations

import asyncio
import getpass
import inspect
import sys

from pwdlib import PasswordHash

from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos.identity_dtos import CreateProfileInput
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory  # noqa: TCH001

_password_hash = PasswordHash.recommended()


def _read_email() -> Email:
    while True:
        raw = input("Email: ").strip()
        try:
            return Email(raw)
        except Exception as e:
            # Domain validation surfaces as a generic exception; print the
            # message so the user knows what to fix and re-prompt.
            print(f"  invalid: {e}")


def _read_password() -> str:
    while True:
        first = getpass.getpass("Password: ")
        if len(first) < 8:
            print("  password must be at least 8 characters")
            continue
        second = getpass.getpass("Confirm:  ")
        if first != second:
            print("  passwords do not match — try again")
            continue
        return first


def _read_profile_name() -> str:
    raw = input("Default profile name [Admin]: ").strip()
    return raw or "Admin"


async def _resolve_uow_factory(provider):  # type: ignore[no-untyped-def]
    """Resolve a dependency-injector provider to its concrete factory.

    Provider invocation returns a ``Future`` in production (because
    of the ``providers.Resource`` session_factory dependency); in
    tests it returns synchronously when overridden as
    ``providers.Object``. ``isawaitable`` covers both shapes.
    """
    result = provider()
    if inspect.isawaitable(result):
        result = await result
    return result


async def _snapshot_library_ids(library_uow_factory: LibraryUnitOfWorkFactory) -> list[str]:
    """Return the prefixed external_ids of every active library."""
    async with library_uow_factory() as uow:
        libraries = await uow.libraries.find_all()
    return [str(library.id) for library in libraries if library.id is not None]


async def _bootstrap_admin() -> None:
    email = _read_email()
    password = _read_password()
    profile_name = _read_profile_name()

    container = ApplicationContainer()
    await container.infrastructure.init_resources()

    try:
        identity_uow_factory = await _resolve_uow_factory(
            container.identity.identity_unit_of_work_factory,
        )
        async with identity_uow_factory() as uow:
            existing = await uow.users.find_by_email(email)
            if existing is not None:
                print(f"  refusing to overwrite existing user {existing.id}")
                sys.exit(1)

            hashed = _password_hash.hash(password)
            admin = User.create(
                email=email,
                role=UserRole.ADMIN,
                is_superuser=True,
                is_verified=True,
                hashed_password=hashed,
            )
            saved = await uow.users.save(admin)

        if saved.id is None:
            raise RuntimeError("user id was not assigned during save")

        # Snapshot every currently-registered library and grant the
        # new admin access to all of them. Otherwise the domain's
        # default-deny on ``allowed_library_ids`` would leave the
        # operator with an empty catalog on first login.
        library_uow_factory = await _resolve_uow_factory(
            container.library.library_unit_of_work_factory,
        )
        library_ids = await _snapshot_library_ids(library_uow_factory)

        create_profile = container.identity.create_profile()
        if inspect.isawaitable(create_profile):
            create_profile = await create_profile
        profile = await create_profile.execute(
            CreateProfileInput(
                user_id=saved.id.value,
                name=profile_name,
                allowed_library_ids=library_ids,
            ),
        )

        print(f"created admin {saved.id}")
        print(f"created default profile {profile.id} ({profile.name!r})")
        if library_ids:
            print(f"  granted access to {len(library_ids)} libraries: {', '.join(library_ids)}")
        else:
            print("  no libraries registered yet — admin will see an empty catalog")
            print("  until libraries are created. Re-run identity_grant_all_libraries.py")
            print("  after creating libraries, or grant via PUT /api/v1/profiles/{id}.")
    finally:
        await container.infrastructure.shutdown_resources()


def main() -> None:
    """Synchronous CLI entry point."""
    try:
        asyncio.run(_bootstrap_admin())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
