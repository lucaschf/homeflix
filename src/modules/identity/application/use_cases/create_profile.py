"""CreateProfileUseCase."""

from collections.abc import Callable
from datetime import datetime

from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    ProfileOutput,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._profile_gate import (
    lock_account,
    read_gate_session,
    refuse_limit_without_pin,
    spend_unlock,
    utc_now,
)
from src.modules.identity.application.use_cases._to_output import profile_to_output
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.errors import ParentalPinNotConfiguredError
from src.modules.identity.domain.services.parental_gate import ParentalGate
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.user_id import UserId


class CreateProfileUseCase:
    """Create a new profile owned by the caller.

    The account must exist: an unknown ``user_id`` raises
    ``UserNotFoundException`` (HTTP 404). Authenticated callers can only
    ever pass their own ``user_id`` (sourced from the session), so this
    only happens to an account deleted meanwhile.

    The new profile's maturity limit is guarded by the parental gate
    (ADR-035, Amendment 7): on an account without a PIN a limit is refused
    with ``ParentalPinNotConfiguredError`` (HTTP 409); on an account with
    one, a profile whose limit exceeds the one the session acts under needs
    an unlock on this device, which the creation spends →
    ``ParentalPinRequiredError`` (HTTP 403). The gate runs before the
    profile is saved.

    **Atomicity.** The Unit of Work opens with the account lock
    (``lock_account``), which is also where an account deleted meanwhile
    answers 404: the session, the account's profiles and the PIN the gate
    reads stay as read until the creation commits, since every other profile
    or PIN change of the account waits for it. Underneath, as defence in
    depth, a limited profile is inserted with its limit and then, in the same
    transaction, confirmed by the compare-and-set that guards every limit
    write (``set_maturity_limit`` to the same limit), which takes effect
    only while the account has a PIN; when it does not, the creation is
    refused with ``ParentalPinNotConfiguredError`` and the insert rolled
    back. SQLite admits one writer at a time, so a PIN removal either
    committed before that statement (which then finds no PIN) or runs after
    this transaction commits and finds the limited profile.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, input_dto: CreateProfileInput) -> ProfileOutput:
        """Persist a new profile and return its full representation."""
        caller_id = UserId(input_dto.user_id)
        profile = Profile.create(
            user_id=caller_id,
            name=ProfileName(input_dto.name),
            avatar_url=input_dto.avatar_url,
            allowed_library_ids=input_dto.allowed_library_ids,
            maturity_limit=(
                None if input_dto.maturity_limit is None else AgeRating(input_dto.maturity_limit)
            ),
        )
        async with self._uow_factory() as uow:
            await lock_account(uow, caller_id)
            session = await read_gate_session(uow, caller_id, input_dto.session_token)
            refuse_limit_without_pin(session, before=None, after=profile.maturity_limit)
            if session.pin_configured and ParentalGate.exceeds(
                profile.maturity_limit, session.limit
            ):
                await spend_unlock(uow, session, now=self._clock())

            saved = await uow.profiles.save(profile)
            if saved is None:
                # ``save`` refuses only a soft-deleted profile; this one is new.
                raise RuntimeError("A new profile was refused as soft-deleted")
            limit = saved.maturity_limit
            if (
                limit is not None
                and saved.id is not None
                and not await uow.profiles.set_maturity_limit(saved.id, expected=limit, new=limit)
            ):
                raise ParentalPinNotConfiguredError(
                    message="A maturity limit needs a parental PIN on the account",
                )
        return profile_to_output(saved)


__all__ = ["CreateProfileUseCase"]
