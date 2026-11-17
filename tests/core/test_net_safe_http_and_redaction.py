"""Tests for shared SSRF / public-IP DNS pinning and Telegram URL token redaction."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from homeagentp_core.logging import SecretRedactingFilter, redact_text
from homeagentp_core.net import safe_http


def test_public_ip_only_policy_rejects_private_loopback_metadata_and_mapped_ipv6() -> None:
    for blocked in (
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "192.168.1.50",
        "169.254.169.254",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "0.0.0.0",  # noqa: S104
    ):
        with pytest.raises(safe_http.NetworkSecurityError) as exc_info:
            safe_http.resolve_and_validate_host(blocked, 443, require_public_ip=True)
        assert exc_info.value.code == "ssrf_blocked"

    # Public IP (e.g. Telegram API range) is permitted
    assert safe_http.resolve_and_validate_host("149.154.167.220", 443, require_public_ip=True) == [
        "149.154.167.220"
    ]


def test_build_pinned_transport_fails_closed_on_incompatible_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyPool:
        pass

    monkeypatch.setattr(safe_http.httpcore, "ConnectionPool", DummyPool)
    with pytest.raises(safe_http.NetworkSecurityError) as exc_info:
        safe_http.build_pinned_transport(require_public_ip=True)
    assert exc_info.value.code == "ssrf_pinning_unavailable"


def test_telegram_bot_url_and_token_redaction() -> None:
    sample_bot_val = "123456789:AAH_FakeTelegramToken_ABCDEF1234567"
    raw_url = f"https://api.telegram.org/bot{sample_bot_val}/sendMessage"
    redacted = redact_text(f"Request failed for {raw_url} with bot{sample_bot_val}")
    assert sample_bot_val not in redacted
    assert "https://api.telegram.org/bot[REDACTED]/sendMessage" in redacted

    record = logging.LogRecord(
        name="homeagentp",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Failed calling %s",
        args=(raw_url,),
        exc_info=None,
    )
    record.extra_data = {"telegram_url": raw_url, "bot_token": sample_bot_val}  # type: ignore[attr-defined]
    assert SecretRedactingFilter().filter(record) is True
    assert sample_bot_val not in str(record.msg)
    extra: Any = record.extra_data  # type: ignore[attr-defined]
    assert sample_bot_val not in str(extra)
