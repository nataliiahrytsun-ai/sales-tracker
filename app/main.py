"""FastAPI application entry point."""

from fastapi import FastAPI

from app.routes.health import router as health_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Sales Vibes")
    application.include_router(health_router)
    return application


app = create_app()
