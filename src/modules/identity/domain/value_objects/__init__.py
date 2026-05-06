"""Identity domain value objects.

``ProfileId`` and ``UserId`` live in ``src.shared_kernel.value_objects``
because every consumer bounded context (``watch_progress``,
``collections``, ``preferences``) references those IDs to scope
per-profile data — promoting them avoids a cross-module domain import
that would violate ADR-009. Identity-specific VOs (``Email``,
``ProfileName``, ``UserRole``) stay here because no other BC needs
their semantics.
"""

from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.domain.value_objects.user_role import UserRole

__all__ = ["Email", "ProfileName", "UserRole"]
