"""Grant a profile access to every currently-registered library.

Useful when an existing profile was created before this PR's
default-grant behaviour shipped (or before any libraries were
registered): its ``allowed_library_ids`` is empty and the catalog
returns nothing under the per-profile ACL filter (PR #178). Run
this script to refresh the snapshot — same semantics as
``PUT /api/v1/profiles/{id}`` with an explicit list, including the
revoke-anything-not-in-the-snapshot side effect (intentional:
this is the "sync to current state" tool, not "additive grant").

Run from the project root with the virtualenv active::

    poetry run python scripts/identity_grant_all_libraries.py
    poetry run python scripts/identity_grant_all_libraries.py --profile-id prf_xxxxxxxxxxxx

A bulk ``--all`` mode is intentionally out of scope until the
profile repository exposes a list-all method — operator-only
maintenance and per-profile invocations cover the immediate need.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import sys

from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos.identity_dtos import UpdateProfileInput
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory  # noqa: TCH001
from src.shared_kernel.value_objects.profile_id import ProfileId


async def _resolve(provider):  # type: ignore[no-untyped-def]
    """Resolve a provider to its concrete value, awaiting if needed."""
    result = provider()
    if inspect.isawaitable(result):
        result = await result
    return result


async def _snapshot_library_ids(library_uow_factory: LibraryUnitOfWorkFactory) -> list[str]:
    """Return prefixed external_ids of every active library."""
    async with library_uow_factory() as uow:
        libraries = await uow.libraries.find_all()
    return [str(library.id) for library in libraries if library.id is not None]


async def _grant_one(
    container: ApplicationContainer,
    profile_id: str,
    library_ids: list[str],
) -> None:
    """Grant ``library_ids`` to a single profile via the update use case."""
    # The update use case enforces ownership: ``user_id`` must match
    # the profile's owner. Resolve it via the identity UoW so this
    # script can operate on any profile regardless of caller.
    identity_uow_factory = await _resolve(container.identity.identity_unit_of_work_factory)
    async with identity_uow_factory() as uow:
        target = await uow.profiles.find_by_id(ProfileId(profile_id))
    if target is None:
        print(f"  profile {profile_id} not found")
        sys.exit(1)

    update_profile = container.identity.update_profile()
    if inspect.isawaitable(update_profile):
        update_profile = await update_profile

    await update_profile.execute(
        UpdateProfileInput(
            user_id=target.user_id.value,
            profile_id=profile_id,
            allowed_library_ids=library_ids,
        ),
    )
    print(f"  granted {len(library_ids)} libraries to {profile_id}")


async def _run(profile_id: str | None) -> None:
    container = ApplicationContainer()
    await container.infrastructure.init_resources()

    try:
        library_uow_factory = await _resolve(container.library.library_unit_of_work_factory)
        library_ids = await _snapshot_library_ids(library_uow_factory)
        if not library_ids:
            print("no libraries registered yet — nothing to grant")
            return

        print(f"current libraries: {', '.join(library_ids)}")

        target = profile_id or input("Profile ID (prf_xxxxxxxxxxxx): ").strip()
        if not target:
            print("no profile id supplied; aborting")
            sys.exit(1)
        await _grant_one(container, target, library_ids)
    finally:
        await container.infrastructure.shutdown_resources()


def main() -> None:
    """Synchronous CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-id",
        help="Prefixed external id (prf_xxxxxxxxxxxx) of the target profile. "
        "Prompts interactively when omitted.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_run(args.profile_id))
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
