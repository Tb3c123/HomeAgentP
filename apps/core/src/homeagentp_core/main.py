"""Main FastAPI application factory for HomeAgentP Core."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from homeagentp_core import __version__
from homeagentp_core.auth.router import router as auth_router
from homeagentp_core.auth.security import ensure_admin_user
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.logging import configure_logging
from homeagentp_core.modules.health.router import router as health_router
from homeagentp_core.modules.media.router import router as media_router
from homeagentp_core.modules.media.scheduler import MediaCollectionScheduler
from homeagentp_core.modules.nas.router import router as nas_router
from homeagentp_core.modules.nas.scheduler import NasCollectionScheduler
from homeagentp_core.modules.reports.router import router as reports_router
from homeagentp_core.modules.scripts.router import router as scripts_router
from homeagentp_core.modules.tasks.router import router as tasks_router
from homeagentp_core.seed import seed_example_data


def initialize_core_state(settings: Settings) -> None:
    """Apply migrations, ensure admin account exists, and seed baseline manifests."""
    logger = configure_logging()
    with db_session(settings.db_path) as conn:
        applied = apply_migrations(conn)
        ensure_admin_user(conn, settings)
        seed_example_data(conn, settings)
    logger.info(
        "HomeAgentP Core initialized",
        extra={
            "extra_data": {
                "env": settings.env,
                "db_path": str(settings.db_path),
                "migrations_applied": applied,
                "secret_key": settings.secret_key,  # Automatically redacted by filter
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the HomeAgentP Core FastAPI application.

    Note (F04, P02-F02 & Phase 03): initialize_core_state(), NasCollectionScheduler, and
    MediaCollectionScheduler are managed exclusively inside the FastAPI lifespan context manager.
    """
    resolved_settings = settings if settings is not None else Settings()  # type: ignore[call-arg]
    nas_scheduler = NasCollectionScheduler(resolved_settings)
    media_scheduler = MediaCollectionScheduler(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_core_state(resolved_settings)
        app.state.init_count = getattr(app.state, "init_count", 0) + 1
        await nas_scheduler.start()
        await media_scheduler.start()
        try:
            yield
        finally:
            await media_scheduler.stop()
            await nas_scheduler.stop()

    app = FastAPI(
        title="HomeAgentP Core API",
        version=__version__,
        description=(
            "HomeAgentP B+ Core service: NAS Guardian read-only telemetry, "
            "Media/Downloads read-only hub, Home Assistant & Telegram foundation, "
            "Tasks, and read-only Script Registry."
        ),
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.nas_scheduler = nas_scheduler
    app.state.media_scheduler = media_scheduler
    app.state.init_count = 0

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(nas_router)
    app.include_router(media_router)
    app.include_router(tasks_router)
    app.include_router(scripts_router)
    app.include_router(reports_router)

    return app
