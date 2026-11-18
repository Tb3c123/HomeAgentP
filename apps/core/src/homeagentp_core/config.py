"""Configuration validation for HomeAgentP Core.

Enforces B+ safety boundaries:
- Rejects placeholder or weak secret keys / admin passwords outside isolated unit test overrides.
- Resolves and validates read-only allowlisted directories for scripts and reports.
- Configures read-only NAS Guardian telemetry paths, required mounts, and alert thresholds.
- Never enables consumer Antigravity CLI wrapping or raw Docker socket access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DISALLOWED_PLACEHOLDERS = {
    "",
    "changeme",
    "password",
    "admin",
    "secret",
    "change_me_generate_random_32_byte_secret_key",
    "change_me_strong_local_dev_password",
}

DEFAULT_EXPECTED_SERVICES = [
    "jellyfin",
    "sonarr",
    "radarr",
    "bazarr",
    "prowlarr",
    "seerr",
    "qbittorrent",
    "adguard",
    "portainer",
]

DEFAULT_MEDIA_ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "::1",
    "jellyfin",
    "qbittorrent",
    "sonarr",
    "radarr",
    "bazarr",
    "prowlarr",
    "seerr",
    "jellyseerr",
    "overseerr",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOMEAGENTP_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "testing", "staging", "production"] = "development"
    port: int = Field(default=8310, ge=1024, le=65535)
    core_host: str = "127.0.0.1"
    core_port: int = Field(default=8311, ge=1024, le=65535)

    db_path: Path = Path("./data/homeagentp.db")

    secret_key: str = Field(..., min_length=16)
    admin_username: str = Field(default="admin", min_length=3, max_length=64)
    admin_password: str = Field(..., min_length=8)
    session_ttl_seconds: int = Field(default=28800, ge=300, le=604800)
    cookie_secure: bool = False

    scripts_dir: Path = Path("./config/examples/scripts")
    reports_dir: Path = Path("./config/examples/reports")
    seed_examples: bool = True

    # Phase 02 — NAS Guardian read-only telemetry configuration
    nas_adapter_enabled: bool = False
    nas_telemetry_mode: Literal["disabled", "host_snapshot", "direct_host_fs"] = "disabled"
    nas_host_snapshot_rel_path: str = "nas_host_snapshot.json"
    nas_snapshot_max_age_seconds: int = Field(default=180, ge=15, le=86400)
    nas_proc_root: Path = Path("/host/proc")
    nas_root_mount_path: Path = Path("/host/root")
    nas_mount_check_prefix: str = "/host/mounts"
    nas_required_mounts: list[str] = Field(
        default_factory=lambda: ["/mnt/disk1", "/mnt/disk2"]
    )
    nas_expected_services: list[str] = Field(
        default_factory=lambda: list(DEFAULT_EXPECTED_SERVICES)
    )
    nas_container_snapshot_rel_path: str = ""
    nas_scheduler_enabled: bool = False
    nas_collection_interval_seconds: int = Field(default=60, ge=10, le=3600)
    nas_collection_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    nas_min_persist_interval_seconds: int = Field(default=15, ge=0, le=3600)
    nas_history_retention_limit: int = Field(default=120, ge=5, le=2000)

    # Alert thresholds (percentage 1..100)
    nas_cpu_warn_percent: float = Field(default=80.0, ge=1.0, le=100.0)
    nas_cpu_critical_percent: float = Field(default=95.0, ge=1.0, le=100.0)
    nas_ram_warn_percent: float = Field(default=85.0, ge=1.0, le=100.0)
    nas_ram_critical_percent: float = Field(default=95.0, ge=1.0, le=100.0)
    nas_disk_warn_percent: float = Field(default=85.0, ge=1.0, le=100.0)
    nas_disk_critical_percent: float = Field(default=95.0, ge=1.0, le=100.0)
    nas_container_mem_warn_percent: float = Field(default=85.0, ge=1.0, le=100.0)
    nas_container_mem_critical_percent: float = Field(default=95.0, ge=1.0, le=100.0)

    # Phase 03 — Media & Downloads Monitoring Hub configuration
    media_adapter_enabled: bool = False
    media_scheduler_enabled: bool = False
    media_collection_interval_seconds: int = Field(default=90, ge=15, le=3600)
    media_collection_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    media_http_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    media_max_response_bytes: int = Field(default=2_097_152, ge=4096, le=16_777_216)
    media_min_persist_interval_seconds: int = Field(default=30, ge=0, le=3600)
    media_history_retention_limit: int = Field(default=120, ge=5, le=2000)
    media_snapshot_stale_seconds: int = Field(default=300, ge=30, le=86400)
    media_failure_threshold: int = Field(default=3, ge=1, le=20)
    media_allowed_hosts: list[str] = Field(
        default_factory=lambda: list(DEFAULT_MEDIA_ALLOWED_HOSTS)
    )

    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    qbittorrent_url: str = ""
    qbittorrent_username: str = ""
    qbittorrent_password: str = ""
    qbittorrent_stalled_threshold_seconds: int = Field(default=1800, ge=60, le=604800)

    sonarr_url: str = ""
    sonarr_api_key: str = ""

    radarr_url: str = ""
    radarr_api_key: str = ""

    bazarr_url: str = ""
    bazarr_api_key: str = ""

    prowlarr_url: str = ""
    prowlarr_api_key: str = ""

    seerr_url: str = ""
    seerr_api_key: str = ""

    # Phase 05 — Read-only Home Assistant & Outbound-only Telegram configuration (opt-in)
    ha_enabled: bool = False
    ha_scheduler_enabled: bool = False
    home_assistant_url: str = ""
    ha_token: str = ""
    ha_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "::1"]
    )
    ha_allowed_entities: list[str] = Field(default_factory=list)
    ha_http_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    ha_collection_interval_seconds: int = Field(default=60, ge=15, le=3600)
    ha_collection_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    ha_max_response_bytes: int = Field(default=524_288, ge=4096, le=4_194_304)
    ha_min_persist_interval_seconds: int = Field(default=30, ge=0, le=3600)
    ha_history_retention_limit: int = Field(default=200, ge=5, le=2000)
    ha_snapshot_stale_seconds: int = Field(default=300, ge=30, le=86400)

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: list[str] = Field(default_factory=list)
    telegram_http_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    notification_scheduler_enabled: bool = False
    notification_poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    notification_cycle_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    notification_outbox_max_active: int = Field(default=100, ge=10, le=1000)
    notification_history_retention_limit: int = Field(default=500, ge=20, le=5000)
    notification_lease_seconds: int = Field(default=60, ge=5, le=600)
    notification_max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() in DISALLOWED_PLACEHOLDERS:
            raise ValueError(
                "HOMEAGENTP_SECRET_KEY uses a disallowed placeholder value. "
                "Provide a unique random secret key."
            )
        return cleaned

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() in DISALLOWED_PLACEHOLDERS:
            raise ValueError(
                "HOMEAGENTP_ADMIN_PASSWORD uses a disallowed placeholder or weak default. "
                "Provide a strong unique password."
            )
        return cleaned

    @model_validator(mode="after")
    def validate_directories_and_thresholds(self) -> Settings:
        for attr_name in ("scripts_dir", "reports_dir"):
            directory: Path = getattr(self, attr_name)
            if directory.exists() and directory.is_symlink():
                raise ValueError(f"{attr_name} ({directory}) must not be a symlink.")
            resolved = directory.resolve()
            if str(resolved) in {"/", "/etc", "/root", "/proc", "/sys", "/var/run"}:
                raise ValueError(f"{attr_name} ({resolved}) points to a restricted system path.")

        if self.nas_cpu_warn_percent >= self.nas_cpu_critical_percent:
            raise ValueError("nas_cpu_warn_percent must be less than nas_cpu_critical_percent.")
        if self.nas_ram_warn_percent >= self.nas_ram_critical_percent:
            raise ValueError("nas_ram_warn_percent must be less than nas_ram_critical_percent.")
        if self.nas_disk_warn_percent >= self.nas_disk_critical_percent:
            raise ValueError("nas_disk_warn_percent must be less than nas_disk_critical_percent.")
        if self.nas_container_mem_warn_percent >= self.nas_container_mem_critical_percent:
            raise ValueError(
                "nas_container_mem_warn_percent must be less than "
                "nas_container_mem_critical_percent."
            )

        cleaned_chats = [c.strip() for c in self.telegram_allowed_chat_ids if c.strip()]
        if len(cleaned_chats) > 1:
            raise ValueError(
                "Phase 05 MVP supports at most one configured Telegram destination in "
                "HOMEAGENTP_TELEGRAM_ALLOWED_CHAT_IDS."
            )
        return self

    def redacted_summary(self) -> dict[str, object]:
        """Return safe configuration metadata for the Settings UI without exposing secrets."""
        return {
            "env": self.env,
            "port": self.port,
            "core_host": self.core_host,
            "core_port": self.core_port,
            "db_path": str(self.db_path),
            "admin_username": self.admin_username,
            "session_ttl_seconds": self.session_ttl_seconds,
            "cookie_secure": self.cookie_secure,
            "scripts_dir": str(self.scripts_dir),
            "reports_dir": str(self.reports_dir),
            "seed_examples": self.seed_examples,
            "secret_key": "[REDACTED]",
            "admin_password": "[REDACTED]",
            "jellyfin_api_key": "[REDACTED]" if self.jellyfin_api_key else "not_configured",
            "qbittorrent_password": (
                "[REDACTED]" if self.qbittorrent_password else "not_configured"
            ),
            "sonarr_api_key": "[REDACTED]" if self.sonarr_api_key else "not_configured",
            "radarr_api_key": "[REDACTED]" if self.radarr_api_key else "not_configured",
            "bazarr_api_key": "[REDACTED]" if self.bazarr_api_key else "not_configured",
            "prowlarr_api_key": "[REDACTED]" if self.prowlarr_api_key else "not_configured",
            "seerr_api_key": "[REDACTED]" if self.seerr_api_key else "not_configured",
            "ha_token": "[REDACTED]" if self.ha_token else "not_configured",
            "telegram_bot_token": "[REDACTED]" if self.telegram_bot_token else "not_configured",
            "architecture_mode": "B+ (Antigravity-first, Dashboard-light)",
            "script_execution_enabled": False,
            "docker_socket_mounted": False,
            "antigravity_cli_wrapper": "prohibited",
            "nas_guardian": {
                "adapter_enabled": self.nas_adapter_enabled,
                "telemetry_mode": self.nas_telemetry_mode,
                "host_snapshot_rel_path": (
                    self.nas_host_snapshot_rel_path or "not_configured"
                ),
                "snapshot_max_age_seconds": self.nas_snapshot_max_age_seconds,
                "proc_root": str(self.nas_proc_root),
                "root_mount_path": str(self.nas_root_mount_path),
                "required_mounts": self.nas_required_mounts,
                "expected_services": self.nas_expected_services,
                "container_snapshot_rel_path": (
                    self.nas_container_snapshot_rel_path or "not_configured"
                ),
                "scheduler_enabled": self.nas_scheduler_enabled,
                "collection_interval_seconds": self.nas_collection_interval_seconds,
                "collection_timeout_seconds": self.nas_collection_timeout_seconds,
                "min_persist_interval_seconds": self.nas_min_persist_interval_seconds,
                "history_retention_limit": self.nas_history_retention_limit,
                "thresholds": {
                    "cpu_warn_percent": self.nas_cpu_warn_percent,
                    "cpu_critical_percent": self.nas_cpu_critical_percent,
                    "ram_warn_percent": self.nas_ram_warn_percent,
                    "ram_critical_percent": self.nas_ram_critical_percent,
                    "disk_warn_percent": self.nas_disk_warn_percent,
                    "disk_critical_percent": self.nas_disk_critical_percent,
                    "container_mem_warn_percent": self.nas_container_mem_warn_percent,
                    "container_mem_critical_percent": self.nas_container_mem_critical_percent,
                },
            },
            "media_hub": {
                "adapter_enabled": self.media_adapter_enabled,
                "scheduler_enabled": self.media_scheduler_enabled,
                "collection_interval_seconds": self.media_collection_interval_seconds,
                "collection_timeout_seconds": self.media_collection_timeout_seconds,
                "http_timeout_seconds": self.media_http_timeout_seconds,
                "max_response_bytes": self.media_max_response_bytes,
                "min_persist_interval_seconds": self.media_min_persist_interval_seconds,
                "history_retention_limit": self.media_history_retention_limit,
                "snapshot_stale_seconds": self.media_snapshot_stale_seconds,
                "failure_threshold": self.media_failure_threshold,
                "allowed_hosts": self.media_allowed_hosts,
                "qbittorrent_stalled_threshold_seconds": (
                    self.qbittorrent_stalled_threshold_seconds
                ),
            },
            "integrations": {
                "nas_guardian": "configured" if self.nas_adapter_enabled else "unavailable",
                "jellyfin": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.jellyfin_url
                        and self.jellyfin_api_key
                    )
                    else "unavailable"
                ),
                "sonarr": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.sonarr_url
                        and self.sonarr_api_key
                    )
                    else "unavailable"
                ),
                "radarr": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.radarr_url
                        and self.radarr_api_key
                    )
                    else "unavailable"
                ),
                "bazarr": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.bazarr_url
                        and self.bazarr_api_key
                    )
                    else "unavailable"
                ),
                "prowlarr": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.prowlarr_url
                        and self.prowlarr_api_key
                    )
                    else "unavailable"
                ),
                "seerr": (
                    "configured"
                    if bool(
                        self.media_adapter_enabled
                        and self.seerr_url
                        and self.seerr_api_key
                    )
                    else "unavailable"
                ),
                "qbittorrent": (
                    "configured"
                    if bool(self.media_adapter_enabled and self.qbittorrent_url)
                    else "unavailable"
                ),
                "home_assistant": "configured" if bool(self.home_assistant_url) else "unavailable",
                "telegram": "configured" if bool(self.telegram_bot_token) else "unavailable",
            },
        }
