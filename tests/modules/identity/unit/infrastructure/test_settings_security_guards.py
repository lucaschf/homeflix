"""Tests for the cross-field security validators on ``Settings``.

These guards are load-bearing — the placeholder secret_key and the
default ``session_cookie_secure=False`` are convenient for dev but
security risks in production. The validator ensures the process
refuses to start with either of them when ``app_env`` is set to
``production``.
"""

import pytest
from pydantic import SecretStr, ValidationError

from src.config.settings import Settings


class TestProductionConfigGuards:
    def test_should_accept_dev_defaults(self):
        # Development environment: placeholder secret + insecure cookie are
        # both fine. Sanity check that the validator does not over-trigger.
        settings = Settings(app_env="development")

        assert settings.is_development is True
        # No exception raised.

    def test_should_reject_placeholder_secret_in_production(self):
        with pytest.raises(ValidationError, match="secret_key.*placeholder"):
            Settings(app_env="production", session_cookie_secure=True)

    def test_should_reject_insecure_cookie_in_production(self):
        with pytest.raises(ValidationError, match="session_cookie_secure"):
            Settings(
                app_env="production",
                secret_key=SecretStr("strong-secret-32-chars-or-more-yes"),
                session_cookie_secure=False,
            )

    def test_should_accept_hardened_production_config(self):
        settings = Settings(
            app_env="production",
            secret_key=SecretStr("strong-secret-32-chars-or-more-yes"),
            session_cookie_secure=True,
        )

        assert settings.is_production is True
        assert settings.session_cookie_secure is True
        # Secret is wrapped — repr should not echo the raw value.
        assert "strong-secret" not in repr(settings)


class TestSecretStrMasking:
    def test_secret_key_should_not_appear_in_repr(self):
        # Even in dev, the SecretStr wrapper should keep the value out
        # of casual logging.
        settings = Settings(app_env="development")

        assert "CHANGE-ME-IN-PRODUCTION" not in repr(settings)
        # And get_secret_value still returns the actual string.
        assert settings.secret_key.get_secret_value() == "CHANGE-ME-IN-PRODUCTION"
