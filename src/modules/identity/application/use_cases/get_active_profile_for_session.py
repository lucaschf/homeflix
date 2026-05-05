"""GetActiveProfileForSessionUseCase."""

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory


class GetActiveProfileForSessionUseCase:
    """Resolve a session token to its currently-active profile id.

    Read-only projection over ``access_tokens.current_profile_id``,
    consumed by ``GET /api/v1/users/me`` so the frontend learns
    which profile the session is scoped to without keeping its own
    mirror. Returns the prefixed external id (``prf_xxx``) — the
    repository's snapshot already translates the on-disk UUID, so
    the use case is just a thin pass-through.

    Returns ``None`` when:

    - the token is unknown (cookie was forged or already revoked), or
    - the token exists but no profile has been selected yet
      (post-login, pre-picker — every user with a fresh login lands
      here until they hit ``POST /profiles/{id}/switch``).

    Both branches collapse to ``None`` on purpose: the route caller
    does not need to distinguish "session gone" from "profile not
    chosen" — the only consumer is a UI hint, and a missing token
    in a request that already passed ``current_active_user`` is a
    self-inconsistent state we don't want to model as a hard error.
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, session_token: str) -> str | None:
        """Return the active profile's prefixed id, or ``None``."""
        async with self._uow_factory() as uow:
            snapshot = await uow.access_tokens.get_by_token(session_token)
        if snapshot is None or snapshot.current_profile_id is None:
            return None
        return str(snapshot.current_profile_id)


__all__ = ["GetActiveProfileForSessionUseCase"]
