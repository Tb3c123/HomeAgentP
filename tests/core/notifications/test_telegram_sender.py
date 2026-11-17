"""Tests for Phase 05 P05-F03: Outbound-only Telegram sendMessage client and SSRF/secrecy."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest
from tests.core.workspace.conftest import make_workspace_settings

from homeagentp_core.config import Settings
from homeagentp_core.modules.notifications.telegram import (
    TelegramConfigError,
    TelegramOutboundSender,
)
from homeagentp_core.net.safe_http import NetworkSecurityError, SafeDnsPinningBackend

FAKE_TOKEN = "999888777:AAFakeBotTokenForUnitTestsOnly_9876543210"  # noqa: S105


def _make_tg_settings(tmp_path: Path, **overrides: object) -> Settings:
    base = make_workspace_settings(tmp_path, db_name="tg_sender.db")
    data = base.model_dump()
    data.update(overrides)
    return Settings(**data)


def test_telegram_disabled_by_default_and_chat_id_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("Network must not be called when Telegram is disabled or unlisted")

    monkeypatch.setattr(httpx.Client, "stream", fail_network)

    disabled_settings = _make_tg_settings(tmp_path, telegram_enabled=False)
    with pytest.raises(TelegramConfigError) as exc_dis:
        TelegramOutboundSender.from_settings(disabled_settings)
    assert exc_dis.value.code == "telegram_disabled"

    with pytest.raises(ValueError, match="at most one"):
        _make_tg_settings(
            tmp_path,
            telegram_enabled=True,
            telegram_bot_token=FAKE_TOKEN,
            telegram_allowed_chat_ids=["-100111222333", "-100444555666"],
        )

    with pytest.raises(TelegramConfigError) as exc_multi:
        TelegramOutboundSender(
            bot_token=FAKE_TOKEN,
            allowed_chat_ids=["-100111222333", "-100444555666"],
        )
    assert exc_multi.value.code == "multiple_chat_ids_unsupported"

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
    )
    with pytest.raises(TelegramConfigError) as exc_chat:
        sender.send_message(chat_id="-100999888777", text="Unauthorized chat")
    assert exc_chat.value.code == "chat_id_not_allowlisted"


def test_telegram_send_message_redacts_payload_and_handles_429_4xx_5xx_redirects() -> None:
    seen_requests: list[tuple[str, str, dict[str, object]]] = []

    def ok_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen_requests.append((request.method, request.url.path, body))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    sender_ok = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(ok_handler),
    )
    res_ok = sender_ok.send_message(
        chat_id="-100111222333",
        text="Alert: token=my_secret_value_12345",
    )
    assert res_ok.ok is True
    assert len(seen_requests) == 1
    method, path, payload = seen_requests[0]
    assert method == "POST"
    assert path == f"/bot{FAKE_TOKEN}/sendMessage"
    assert payload["disable_web_page_preview"] is True
    assert "my_secret_value_12345" not in str(payload["text"])

    # HTTP 429 Retry-After header & JSON parameter
    sender_429 = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                429,
                headers={"Retry-After": "45"},
                json={"ok": False, "parameters": {"retry_after": 45}},
            )
        ),
    )
    res_429 = sender_429.send_message(chat_id="-100111222333", text="Rate limited")
    assert res_429.ok is False
    assert res_429.retryable is True
    assert res_429.permanent is False
    assert res_429.retry_after_seconds == 45

    # Permanent 4xx -> permanent=True (dead_letter)
    sender_400 = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(lambda req: httpx.Response(400, json={"ok": False})),
    )
    res_400 = sender_400.send_message(chat_id="-100111222333", text="Bad request")
    assert res_400.ok is False
    assert res_400.permanent is True
    assert res_400.retryable is False

    # Transient 5xx -> retryable=True
    sender_503 = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(lambda req: httpx.Response(503, json={"ok": False})),
    )
    res_503 = sender_503.send_message(chat_id="-100111222333", text="Upstream 503")
    assert res_503.ok is False
    assert res_503.retryable is True
    assert res_503.permanent is False

    # Redirect 302 -> blocked permanently
    sender_redir = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(
            lambda req: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
        ),
    )
    res_redir = sender_redir.send_message(chat_id="-100111222333", text="Redirect test")
    assert res_redir.ok is False
    assert res_redir.permanent is True
    assert res_redir.error_code == "redirect_blocked"


def test_telegram_never_leaks_bot_token_or_url_in_errors_and_blocks_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"Failed connecting to https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage",
            request=request,
        )

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100111222333"],
        transport=httpx.MockTransport(raise_connect_error),
    )
    res = sender.send_message(chat_id="-100111222333", text="Connect error test")
    assert res.ok is False
    assert res.retryable is True
    assert FAKE_TOKEN not in res.error_message
    assert "AAFakeBotToken" not in res.error_message

    # Public-IP-only DNS pinning rejects private/metadata DNS rebinding for api.telegram.org
    def fake_getaddrinfo(
        host: str,
        port: object,
        type: int = 0,
    ) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    backend = SafeDnsPinningBackend(require_public_ip=True)
    with pytest.raises(NetworkSecurityError) as exc:
        backend.connect_tcp("api.telegram.org", 443)
    assert exc.value.code == "ssrf_blocked"
