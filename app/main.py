"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, settings
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.home import router as home_router
from app.routes.meetings import router as meetings_router
from app.routes.outreach import router as outreach_router


def create_app(application_settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    selected_settings = application_settings or settings
    application = FastAPI(title="Sales Tracker")
    application.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parent / "static"),
        name="static",
    )
    application.add_middleware(
        SessionMiddleware,
        secret_key=selected_settings.session_secret,
        session_cookie="sales_tracker_session",
        same_site="lax",
        https_only=selected_settings.session_cookie_secure,
        max_age=selected_settings.session_max_age_seconds,
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(home_router)
    application.include_router(meetings_router)
    application.include_router(outreach_router)
    return application


app = create_app()
