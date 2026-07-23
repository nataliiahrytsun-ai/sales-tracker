"""Application health-check route."""

from typing import Literal

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.logging_config import APPLICATION_LOGGER_NAME
from app.services.readiness import ReadinessChecker, ReadinessError

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, Literal["ok"]]:
    """Report that the application process is responsive."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def readiness_check(request: Request) -> JSONResponse:
    """Report whether the configured database schema is ready."""
    checker: ReadinessChecker = request.app.state.readiness_checker
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    try:
        checker.check()
    except ReadinessError as error:
        logger.warning(
            "Readiness check failed category=%s",
            error.category,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    except Exception:
        logger.error("Readiness check failed category=internal error")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    return JSONResponse(content={"status": "ready"})
