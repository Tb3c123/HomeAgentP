"""Abstract base adapter interface for Phase 03 Media & Downloads services."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.logging import redact_text
from homeagentp_core.modules.media.errors import MediaAdapterError


class MediaServiceAdapter(ABC):
    """Uniform read-only adapter interface for all Phase 03 Media & Downloads services."""

    service_name: str
    title: str
    category: Literal["media", "downloads"]

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @abstractmethod
    def is_configured(self) -> tuple[bool, str]:
        """Return (configured_and_enabled, reason_if_not)."""

    @abstractmethod
    def _empty_metrics(self) -> dict[str, Any]:
        """Return honest empty/unavailable metric structure for this service."""

    @abstractmethod
    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        """Execute read-only API calls and return (status, version, metrics, alerts, reason)."""

    def collect(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Collect a read-only snapshot with full fault isolation and latency measurement."""
        ref_now = now or datetime.now(UTC)
        now_iso = ref_now.isoformat()

        if not self._settings.media_adapter_enabled:
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": False,
                "configured": False,
                "status": "unavailable",
                "error_code": None,
                "reason": (
                    "Media & Downloads monitoring hub is disabled "
                    "(HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false)."
                ),
                "latency_ms": None,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }

        configured, reason = self.is_configured()
        if not configured:
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": False,
                "configured": False,
                "status": "unavailable",
                "error_code": None,
                "reason": reason,
                "latency_ms": None,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }

        start_t = time.monotonic()
        try:
            svc_status, version, metrics, alerts, ok_reason = self._poll_live(now_iso)
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": svc_status,
                "error_code": None,
                "reason": ok_reason,
                "latency_ms": latency_ms,
                "version": version,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": metrics,
                "alerts": alerts,
            }
        except MediaAdapterError as exc:
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": exc.status,
                "error_code": exc.error_code,
                "reason": exc.safe_message,
                "latency_ms": latency_ms,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 1,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            safe_err = redact_text(f"{type(exc).__name__}: {exc}")
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": "error",
                "error_code": "unexpected_error",
                "reason": safe_err,
                "latency_ms": latency_ms,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 1,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }
