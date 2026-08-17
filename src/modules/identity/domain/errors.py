"""Identity domain-level exceptions.

Only genuine domain-invariant violations raised **from the domain layer**
live here (subclassing the domain exception bases). Application-level errors
(not-found, forbidden, unauthorized, conflict) raised by the use cases live
in ``identity/application/errors.py`` — keeping the domain layer free of any
dependency on ``building_blocks.application``.
"""

from dataclasses import dataclass

from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.identity.domain.rule_codes import IdentityRuleCodes


@dataclass
class CannotDemoteLastAdminError(BusinessRuleViolationException):
    """Operation would leave the system with zero active admins.

    A domain invariant — the household must always retain at least one
    active administrator — enforced by the ``admin_quorum`` domain service.
    Fires from both the role-flip (demoting the last admin) and the delete
    (removing the last admin even when not self-targeting) paths.

    Maps to HTTP 409 via ``error_mapping.py`` (keyed on ``code``, ADR-012),
    unchanged by the domain re-base.
    """

    code: str = "USER_CANNOT_DEMOTE_LAST_ADMIN"
    message_code: str = IdentityRuleCodes.USER_CANNOT_DEMOTE_LAST_ADMIN
    rule_code: str = IdentityRuleCodes.USER_CANNOT_DEMOTE_LAST_ADMIN


__all__ = ["CannotDemoteLastAdminError"]
