"""FastAPI application entry point."""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, settings
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.exports import router as exports_router
from app.routes.health import router as health_router
from app.routes.home import router as home_router
from app.routes.meetings import router as meetings_router
from app.routes.my_week import router as my_week_router
from app.routes.outreach import router as outreach_router
from app.routes.targets import router as targets_router
from app.security import (
    LoginRateLimiter,
    SecurityHeadersMiddleware,
    enforce_csrf,
)


def create_app(application_settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    selected_settings = application_settings or settings
    application = FastAPI(
        title="Sales Tracker",
        debug=False,
        dependencies=[Depends(enforce_csrf)],
    )
    application.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=selected_settings.login_rate_limit_max_attempts,
        window_seconds=selected_settings.login_rate_limit_window_seconds,
        block_seconds=selected_settings.login_rate_limit_block_seconds,
    )
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
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(selected_settings.allowed_hosts),
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(dashboard_router)
    application.include_router(exports_router)
    application.include_router(home_router)
    application.include_router(meetings_router)
    application.include_router(my_week_router)
    application.include_router(outreach_router)
    application.include_router(targets_router)
    return application


app = create_app()
