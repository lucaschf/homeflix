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
   ``CreateProfileUseCase`` so ``get_current_profile`` resolves on
   the first login.

Bootstrap path lives in ``scripts/`` rather than as a public route
because PR 1 deliberately does not expose ``/auth/register`` —
self-service registration UX is undefined and admin-creation is a
once-per-deployment action. See ADR-010 / ADR-011 for the framing.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from pwdlib import PasswordHash

from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos.identity_dtos import CreateProfileInput
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole

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


async def _bootstrap_admin() -> None:
    email = _read_email()
    password = _read_password()
    profile_name = _read_profile_name()

    container = ApplicationContainer()
    await container.infrastructure.init_resources()

    try:
        uow_factory = container.identity.identity_unit_of_work_factory()
        async with uow_factory() as uow:
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

        create_profile = container.identity.create_profile()
        profile = await create_profile.execute(
            CreateProfileInput(user_id=saved.id.value, name=profile_name),
        )

        print(f"created admin {saved.id}")
        print(f"created default profile {profile.id} ({profile.name!r})")
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
