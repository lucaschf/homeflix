"""Pydantic request schemas for the admin user endpoints."""

from pydantic import BaseModel, Field


class CreateAdminUserRequest(BaseModel):
    """Body for ``POST /api/v1/admin/users``.

    ``password`` is the *initial* credential set by the operator;
    the user is expected to change it from ``/settings`` after
    their first login. ``role`` defaults to ``member`` so promoting
    a fresh account to admin is a deliberate operator choice.
    """

    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="member")


class UpdateUserRoleRequest(BaseModel):
    """Body for ``PATCH /api/v1/admin/users/{user_id}``.

    The endpoint is single-purpose today (role flip), so the body
    is just the new role. If more fields land later (``is_active``
    suspension, email rewrite) we extend this schema rather than
    splitting the route.
    """

    role: str


__all__ = ["CreateAdminUserRequest", "UpdateUserRoleRequest"]
