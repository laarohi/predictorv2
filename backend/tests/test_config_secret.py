"""Tests for the production JWT-secret strength validator (config.Settings)."""

import pytest
from pydantic import ValidationError

from app.config import Settings

_BASE = {"database_url": "postgresql://u:p@localhost:5432/db"}


def test_known_default_secret_rejected_in_production():
    with pytest.raises(ValidationError):
        Settings(
            **_BASE,
            jwt_secret_key="super-secret-dev-key-change-in-prod",
            debug=False,
        )


def test_short_secret_rejected_in_production():
    with pytest.raises(ValidationError):
        Settings(**_BASE, jwt_secret_key="too-short", debug=False)


def test_strong_secret_accepted_in_production():
    strong = "x" * 48
    settings = Settings(**_BASE, jwt_secret_key=strong, debug=False)
    assert settings.jwt_secret_key == strong


def test_weak_secret_allowed_in_debug():
    # Dev/test ergonomics: the validator is production-only.
    settings = Settings(**_BASE, jwt_secret_key="test-secret-key", debug=True)
    assert settings.debug is True
