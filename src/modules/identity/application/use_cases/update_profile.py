"""UpdateProfileUseCase."""

from collections.abc import Callable
from datetime import datetime

from src.building_blocks.domain.errors import DomainConflictException
from src.modules.identity.application.dtos.identity_dtos import (
    ProfileOutput,
    UpdateProfileInput,
)
from src.modules.identity.application.errors import (
    ProfileNotFoundException,
    ProfileOwnershipViolation,
    UserNotFoundException,
)
from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWork,
    IdentityUnitOfWorkFactory,
)
from src.modules.identity.application.use_cases._profile_gate import (
    lock_account,
    read_gate_session,
    refuse_limit_without_pin,
    spend_unlock,
    utc_now,
)
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.modules.identity.domain.errors import ParentalPinNotConfiguredError
from src.modules.identity.domain.services.parental_gate import ParentalGate
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class UpdateProfileUseCase:
    """Apply a partial update to an existing profile owned by the caller.

    Enforces ownership: the target profile's ``user_id`` must match
    the caller. Cross-user mutation raises
    :class:`ProfileOwnershipViolation` (HTTP 403). A missing target
    raises :class:`ProfileNotFoundException` (HTTP 404).

    The maturity limit is guarded by the parental gate (ADR-035, Amendment
    7), which compares the limit the update leaves with the one the profile
    had — never whether the field was sent, so a rename passes untouched:

    - on an account without a PIN, setting a limit is refused with
      ``ParentalPinNotConfiguredError`` (HTTP 409);
    - on an account with one, widening the profile, or changing another
      profile's limit from a session acting under a limit, needs an unlock
      on this device, which the update spends → ``ParentalPinRequiredError``
      (HTTP 403);
    - widening also drops every other session off the profile, in the same
      transaction, so a device already on it passes the switch guard again.

    The gate runs after ownership and before any write.

    **Atomicity.** The Unit of Work opens with the account lock
    (``lock_account``; a deleted account → ``UserNotFoundException``, 404),
    before the profile is read: the profile, the session, the account's
    profiles and the PIN the gate decides on stay as read until the update
    commits, since every other profile or PIN change of the account waits
    for it. What follows is defence in depth underneath that lock.

    The limit is not written by ``save``, which never touches
    it on an existing profile: a rename, a library change or an avatar
    decided on an entity read before a concurrent limit change leaves that
    change in place. When the update changes the limit, one compare-and-set
    (``set_maturity_limit``) writes it, in the gate's transaction, only while
    the profile still has the limit the gate decided on and, for a limit,
    while the account still has a PIN. When it does not take effect, the
    profile and the account are read again in the same transaction to
    answer: profile gone → ``ProfileNotFoundException`` (404); account
    gone → ``UserNotFoundException`` (404); a limit on an account without a
    PIN → ``ParentalPinNotConfiguredError`` (409); otherwise the limit
    changed meanwhile → ``DomainConflictException`` (409). Nothing is
    committed then, and a spent unlock is handed back.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, input_dto: UpdateProfileInput) -> ProfileOutput:
        """Apply the supplied subset of fields to the target profile and return it."""
        caller_id = UserId(input_dto.user_id)
        target_id = ProfileId(input_dto.profile_id)

        async with self._uow_factory() as uow:
            await lock_account(uow, caller_id)
            existing = await uow.profiles.find_by_id(target_id)
            if existing is None:
                raise ProfileNotFoundException.for_resource(
                    resource_type="Profile",
                    resource_id=input_dto.profile_id,
                )

            if existing.user_id != caller_id:
                raise ProfileOwnershipViolation(
                    message="You do not own this profile",
                )

            updated = existing
            if input_dto.name is not None:
                updated = updated.with_name(ProfileName(input_dto.name))
            if input_dto.allowed_library_ids is not None:
                updated = updated.with_allowed_library_ids(input_dto.allowed_library_ids)
            if input_dto.maturity_limit is not None:
                new_limit = input_dto.maturity_limit.value
                updated = updated.with_maturity_limit(
                    None if new_limit is None else AgeRating(new_limit)
                )

            before, after = existing.maturity_limit, updated.maturity_limit
            session = await read_gate_session(uow, caller_id, input_dto.session_token)
            refuse_limit_without_pin(session, before=before, after=after)
            unlocked_on = None
            if session.pin_configured and ParentalGate.update_requires_unlock(
                before=before,
                after=after,
                target_is_active=session.active_profile_id == target_id,
                session_limit=session.limit,
            ):
                unlocked_on = await spend_unlock(uow, session, now=self._clock())

            if after != before:
                await self._write_limit(uow, caller_id, target_id, before=before, after=after)

            saved = await uow.profiles.save(updated)
            if saved is None:
                raise ProfileNotFoundException.for_resource(
                    resource_type="Profile",
                    resource_id=input_dto.profile_id,
                )

            # A widening always spent an unlock above.
            if unlocked_on is not None and ParentalGate.exceeds(after, before):
                await uow.access_tokens.detach_profile_sessions(target_id, except_token=unlocked_on)

        return profile_to_output(saved)

    @staticmethod
    async def _write_limit(
        uow: IdentityUnitOfWork,
        caller_id: UserId,
        target_id: ProfileId,
        *,
        before: AgeRating | None,
        after: AgeRating | None,
    ) -> None:
        """Compare-and-set the profile's limit, explaining a write that did not take effect.

        Args:
            uow: The update's active Unit of Work.
            caller_id: The account performing the update.
            target_id: The profile being updated.
            before: The limit the gate decided on.
            after: The limit to store.

        Raises:
            ProfileNotFoundException: If the profile was deleted meanwhile.
            UserNotFoundException: If the account was deleted meanwhile.
            ParentalPinNotConfiguredError: If ``after`` is a limit and the
                account no longer has a PIN.
            DomainConflictException: If the profile's limit is no longer
                ``before``.
        """
        if await uow.profiles.set_maturity_limit(target_id, expected=before, new=after):
            return
        if await uow.profiles.find_by_id(target_id) is None:
            raise ProfileNotFoundException.for_resource(
                resource_type="Profile",
                resource_id=target_id.value,
            )
        owner = await uow.users.find_by_id(caller_id)
        if owner is None:
            raise UserNotFoundException.for_resource("User", caller_id.value)
        if after is not None and not owner.has_parental_pin:
            raise ParentalPinNotConfiguredError(
                message="A maturity limit needs a parental PIN on the account",
            )
        raise DomainConflictException(
            message="The profile's maturity limit changed during the update; try again",
        )


__all__ = ["UpdateProfileUseCase"]
