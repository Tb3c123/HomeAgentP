"""Outbound-only Telegram Bot API sendMessage client (P05-F03).

Security invariants:
- Outbound POST sendMessage to https://api.telegram.org only (no getUpdates, no webhooks).
- Public-IP-only DNS pinning via SafeDnsPinningBackend(require_public_ip=True).
- Explicit chat_id allowlist enforcement.
- Redirects blocked (follow_redirects=False, 3xx rejected).
- Bot token and full Bot API URLs are NEVER logged, returned, or stored in errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.logging import redact_text
from homeagentp_core.net.safe_http import NetworkSecurityError, build_pinned_transport

TELEGRAM_API_HOST = "api.telegram.org"
TELEGRAM_SEND_PATH_TEMPLATE = "/bot{token}/sendMessage"
MAX_TELEGRAM_TEXT_CHARS = 2000
MAX_TELEGRAM_RESPONSE_BYTES = 65_536
MIN_RETRY_AFTER_SECONDS = 1
MAX_RETRY_AFTER_SECONDS = 3600
CHAT_ID_PATTERN = re.compile(r"^-?\d{1,32}$")


class TelegramConfigError(RuntimeError):
    """Fail-closed Telegram configuration or destination validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(redact_text(message))
        self.code = code
        self.message = redact_text(message)


@dataclass(frozen=True)
class TelegramSendResult:
    ok: bool
    retryable: bool
    permanent: bool
    status_code: int | None = None
    retry_after_seconds: int | None = None
    error_code: str = ""
    error_message: str = ""


def validate_telegram_chat_id(chat_id: str, allowed_chat_ids: list[str]) -> str:
    """Validate that chat_id is well-formed and explicitly in the configured allowlist."""
    cleaned = chat_id.strip()
    if not cleaned or not CHAT_ID_PATTERN.match(cleaned):
        raise TelegramConfigError("invalid_chat_id", "Telegram chat_id format is invalid.")
    allowed = {c.strip() for c in allowed_chat_ids if c.strip()}
    if cleaned not in allowed:
        raise TelegramConfigError(
            "chat_id_not_allowlisted",
            "Target Telegram chat_id is not in HOMEAGENTP_TELEGRAM_ALLOWED_CHAT_IDS.",
        )
    return cleaned


def _parse_retry_after(resp: httpx.Response, body_bytes: bytes) -> int:
    header_val = resp.headers.get("Retry-After", "").strip()
    if header_val.isdigit():
        return max(MIN_RETRY_AFTER_SECONDS, min(int(header_val), MAX_RETRY_AFTER_SECONDS))
    try:
        data = json.loads(body_bytes.decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            params = data.get("parameters")
            if isinstance(params, dict) and isinstance(params.get("retry_after"), int):
                val = int(params["retry_after"])
                return max(MIN_RETRY_AFTER_SECONDS, min(val, MAX_RETRY_AFTER_SECONDS))
    except (ValueError, TypeError):
        pass
    return 30


class TelegramOutboundSender:
    """Strict outbound-only Telegram sendMessage sender."""

    def __init__(
        self,
        *,
        bot_token: str,
        allowed_chat_ids: list[str],
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cleaned_token = bot_token.strip()
        if not cleaned_token:
            raise TelegramConfigError("missing_token", "Telegram bot token is not configured.")
        self._bot_token = cleaned_token
        self._allowed_chat_ids = [c.strip() for c in allowed_chat_ids if c.strip()]
        if not self._allowed_chat_ids:
            raise TelegramConfigError(
                "missing_chat_ids",
                "No allowlisted Telegram chat IDs configured.",
            )
        self._timeout_seconds = max(0.5, float(timeout_seconds))
        self._transport = transport

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> TelegramOutboundSender:
        if not settings.telegram_enabled:
            raise TelegramConfigError(
                "telegram_disabled",
                "Telegram notifications are disabled in runtime configuration.",
            )
        return cls(
            bot_token=settings.telegram_bot_token,
            allowed_chat_ids=settings.telegram_allowed_chat_ids,
            timeout_seconds=settings.telegram_http_timeout_seconds,
            transport=transport,
        )

    def send_message(self, *, chat_id: str, text: str) -> TelegramSendResult:
        """Send a single redacted text message to an allowlisted Telegram chat_id."""
        validated_chat_id = validate_telegram_chat_id(chat_id, self._allowed_chat_ids)
        safe_text = redact_text(text.strip())[:MAX_TELEGRAM_TEXT_CHARS]
        if not safe_text:
            return TelegramSendResult(
                ok=False,
                retryable=False,
                permanent=True,
                error_code="empty_message",
                error_message="Refusing to send empty Telegram message.",
            )

        try:
            active_transport = (
                self._transport
                if self._transport is not None
                else build_pinned_transport(require_public_ip=True)
            )
        except NetworkSecurityError as exc:
            return TelegramSendResult(
                ok=False,
                retryable=True,
                permanent=False,
                error_code=exc.code,
                error_message=redact_text(exc.message),
            )

        url = f"https://{TELEGRAM_API_HOST}{TELEGRAM_SEND_PATH_TEMPLATE.format(token=self._bot_token)}"
        payload = {
            "chat_id": validated_chat_id,
            "text": safe_text,
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(
                transport=active_transport,
                timeout=self._timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"Accept": "application/json"},
                ) as resp:
                    if 300 <= resp.status_code < 400:
                        return TelegramSendResult(
                            ok=False,
                            retryable=False,
                            permanent=True,
                            status_code=resp.status_code,
                            error_code="redirect_blocked",
                            error_message=(
                                f"Telegram API redirect blocked (HTTP {resp.status_code})."
                            ),
                        )

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_TELEGRAM_RESPONSE_BYTES:
                            return TelegramSendResult(
                                ok=False,
                                retryable=True,
                                permanent=False,
                                status_code=resp.status_code,
                                error_code="response_too_large",
                                error_message="Telegram API response exceeded size limit.",
                            )
                        chunks.append(chunk)
                    body = b"".join(chunks)

                    if resp.status_code == 200:
                        try:
                            parsed = json.loads(body.decode("utf-8", errors="replace"))
                            if isinstance(parsed, dict) and parsed.get("ok") is True:
                                return TelegramSendResult(
                                    ok=True,
                                    retryable=False,
                                    permanent=False,
                                    status_code=200,
                                )
                        except ValueError:
                            pass
                        return TelegramSendResult(
                            ok=False,
                            retryable=True,
                            permanent=False,
                            status_code=200,
                            error_code="invalid_api_response",
                            error_message="Telegram API returned malformed ok=false/invalid JSON.",
                        )

                    if resp.status_code == 429:
                        retry_after = _parse_retry_after(resp, body)
                        return TelegramSendResult(
                            ok=False,
                            retryable=True,
                            permanent=False,
                            status_code=429,
                            retry_after_seconds=retry_after,
                            error_code="rate_limited",
                            error_message=f"Telegram API HTTP 429 (retry_after={retry_after}s).",
                        )

                    if 400 <= resp.status_code < 500:
                        return TelegramSendResult(
                            ok=False,
                            retryable=False,
                            permanent=True,
                            status_code=resp.status_code,
                            error_code="permanent_client_error",
                            error_message=f"Telegram API permanent HTTP {resp.status_code}.",
                        )

                    return TelegramSendResult(
                        ok=False,
                        retryable=True,
                        permanent=False,
                        status_code=resp.status_code,
                        error_code="upstream_server_error",
                        error_message=f"Telegram API transient HTTP {resp.status_code}.",
                    )
        except NetworkSecurityError as exc:
            return TelegramSendResult(
                ok=False,
                retryable=True,
                permanent=False,
                error_code=exc.code,
                error_message=redact_text(exc.message),
            )
        except httpx.TimeoutException:
            return TelegramSendResult(
                ok=False,
                retryable=True,
                permanent=False,
                error_code="timeout",
                error_message="Telegram API request timed out.",
            )
        except httpx.HTTPError as exc:
            # Never pass raw httpx exception text without redaction (could include request URL)
            safe_exc = redact_text(str(exc))
            return TelegramSendResult(
                ok=False,
                retryable=True,
                permanent=False,
                error_code="http_transport_error",
                error_message=f"Telegram transport error ({type(exc).__name__}): {safe_exc}"[:250],
            )
