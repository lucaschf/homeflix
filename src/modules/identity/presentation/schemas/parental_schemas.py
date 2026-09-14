"""Pydantic request schemas for the parental-control endpoints (ADR-035).

Every secret is a ``SecretStr``: the request model's ``repr()`` prints
``'**********'`` instead of the account password or the PIN. Only that
``repr()`` is masked — frames outside these models (FastAPI's own, for
one) still hold the raw request body. The PIN's format is not checked
here but by the ``ParentalPin`` value object, whose 422 carries no trace
of the value; the request-validation 422 envelope never echoes input
either.
"""

from pydantic import BaseModel, SecretStr


class SetParentalPinRequest(BaseModel):
    """Body for ``PUT /api/v1/parental/pin``.

    ``current_password`` is the account password, required to set or
    replace the PIN (ADR-035, Amendment 7 D3). ``pin`` is the new PIN:
    exactly six digits.
    """

    current_password: SecretStr
    pin: SecretStr


class RemoveParentalPinRequest(BaseModel):
    """Body for ``POST /api/v1/parental/pin/remove``.

    ``current_password`` is the account password, required to remove the
    PIN (ADR-035, Amendment 7 D3).
    """

    current_password: SecretStr


__all__ = ["RemoveParentalPinRequest", "SetParentalPinRequest"]
