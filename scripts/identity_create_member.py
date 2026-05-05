"""Bootstrap a regular (non-admin) household member + default profile.

Run from the project root with the virtualenv active:

    poetry run python scripts/identity_create_member.py

Companion to ``identity_create_admin.py`` — same flow, different role.
Use this to create test accounts for the admin gating (PR #186 / #117)
or to seed additional household members until a self-service / admin
panel registration UX exists.

The script prompts for email, password (twice for confirmation), and
the default profile's display name, then:

1. Initialises the application container (engine + session factory).
2. Hashes the password using ``pwdlib`` — the same hasher FastAPI
   Users uses at login.
3. Creates a ``User`` aggregate with ``role=MEMBER``,
   ``is_superuser=False``, ``is_verified=True`` and persists it via
   ``UserRepository``.
4. Creates a default ``Profile`` for the new member via the
   ``CreateProfileUseCase`` and grants it access to every library
   currently registered. The domain default for
   ``allowed_library_ids`` is the empty list (deny-all) — fine for
   strict provisioning, but not what the operator wants when seeding
   a test member who is supposed to actually browse the catalog.
   Tighten the grant later via ``PUT /api/v1/profiles/{id}``.

Bootstrap path lives in ``scripts/`` rather than as a public route
because PR 1 deliberately does not expose ``/auth/register`` —
self-service registration UX is undefined. See ADR-010 / ADR-011
for the framing.
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
    raw = input("Default profile name [Member]: ").strip()
    return raw or "Member"


async def _resolve_uow_factory(provider):  # type: ignore[no-untyped-def]
    """Resolve a dependency-injector provider to its concrete factory.

    Same shape as ``identity_create_admin._resolve_uow_factory`` —
    invocation returns a ``Future`` in production (because of the
    ``providers.Resource`` session_factory dependency) and resolves
    synchronously in tests where the provider is overridden.
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


async def _bootstrap_member() -> None:
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
            member = User.create(
                email=email,
                role=UserRole.MEMBER,
                is_superuser=False,
                is_verified=True,
                hashed_password=hashed,
            )
            saved = await uow.users.save(member)

        if saved.id is None:
            raise RuntimeError("user id was not assigned during save")

        # Snapshot every currently-registered library and grant the
        # new member access. Default-deny would leave the member with
        # an empty catalog on first login — tighten via
        # ``PUT /api/v1/profiles/{id}`` afterwards if a more
        # restrictive ACL is wanted.
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

        print(f"created member {saved.id}")
        print(f"created default profile {profile.id} ({profile.name!r})")
        if library_ids:
            print(f"  granted access to {len(library_ids)} libraries: {', '.join(library_ids)}")
        else:
            print("  no libraries registered yet — member will see an empty catalog")
            print("  until libraries are created and granted via PUT /api/v1/profiles/{id}.")
    finally:
        await container.infrastructure.shutdown_resources()


def main() -> None:
    """Synchronous CLI entry point."""
    try:
        asyncio.run(_bootstrap_member())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
