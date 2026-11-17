"""Tests for configuration validation errors and structured log secret redaction."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from homeagentp_core.config import Settings
from homeagentp_core.logging import redact_structure, redact_text


def test_config_rejects_placeholder_or_weak_secrets(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            db_path=tmp_path / "db.sqlite",
            secret_key="CHANGE_ME_GENERATE_RANDOM_32_BYTE_SECRET_KEY",  # noqa: S106
            admin_password="ValidPassword123!",  # noqa: S106
        )

    with pytest.raises(ValidationError):
        Settings(
            db_path=tmp_path / "db.sqlite",
            secret_key="valid_random_secret_key_for_test_12345",  # noqa: S106
            admin_password="CHANGE_ME_STRONG_LOCAL_DEV_PASSWORD",  # noqa: S106
        )

    with pytest.raises(ValidationError):
        Settings(
            db_path=tmp_path / "db.sqlite",
            secret_key="short",  # noqa: S106
            admin_password="ValidPassword123!",  # noqa: S106
        )


def test_config_rejects_symlink_scripts_dir(tmp_path: Path) -> None:
    real_dir = tmp_path / "real_scripts"
    real_dir.mkdir()
    symlink_dir = tmp_path / "symlink_scripts"
    symlink_dir.symlink_to(real_dir)

    with pytest.raises(ValidationError):
        Settings(
            db_path=tmp_path / "db.sqlite",
            secret_key="valid_random_secret_key_for_test_12345",  # noqa: S106
            admin_password="ValidPassword123!",  # noqa: S106
            scripts_dir=symlink_dir,
        )


def test_log_redaction_scrubs_secrets_and_tokens() -> None:
    raw_msg = (
        "Connecting with password=MySuperSecret123 and "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 "
        "cookie homeagentp_session=raw_cookie_token_value"
    )
    redacted = redact_text(raw_msg)
    assert "MySuperSecret123" not in redacted
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "raw_cookie_token_value" not in redacted
    assert "[REDACTED]" in redacted

    nested = {
        "user": "admin",
        "admin_password": "plain_password",
        "telegram_bot_token": "123456:ABCDEF",
        "nested": {"csrf_token": "secret_csrf", "safe_field": "kept"},
    }
    sanitized = redact_structure(nested)
    assert sanitized["admin_password"] == "[REDACTED]"  # noqa: S105
    assert sanitized["telegram_bot_token"] == "[REDACTED]"  # noqa: S105
    assert sanitized["nested"]["csrf_token"] == "[REDACTED]"  # noqa: S105
    assert sanitized["nested"]["safe_field"] == "kept"
