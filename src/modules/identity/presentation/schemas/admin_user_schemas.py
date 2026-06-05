"""Pydantic request schemas for the admin user endpoints.

``role`` fields are typed with the ``UserRole`` enum (ADR-018): an
invalid role fails validation at the HTTP boundary as a 422 — with
the allowed values documented in the OpenAPI schema — instead of
travelling through the application layer as a raw string and blowing
up inside the use case.
"""

from pydantic import BaseModel, Field

from src.modules.identity.domain.value_objects.user_role import UserRole


class CreateAdminUserRequest(BaseModel):
    """Body for ``POST /api/v1/admin/users``.

    ``password`` is the *initial* credential set by the operator;
    the user is expected to change it from ``/settings`` after
    their first login. ``role`` defaults to ``member`` so promoting
    a fresh account to admin is a deliberate operator choice.
    """

    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = Field(default=UserRole.MEMBER)


class UpdateUserRoleRequest(BaseModel):
    """Body for ``PATCH /api/v1/admin/users/{user_id}``.

    The endpoint is single-purpose today (role flip), so the body
    is just the new role. If more fields land later (``is_active``
    suspension, email rewrite) we extend this schema rather than
    splitting the route.
    """

    role: UserRole


__all__ = ["CreateAdminUserRequest", "UpdateUserRoleRequest"]
