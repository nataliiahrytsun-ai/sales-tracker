"""Application health-check route."""

from typing import Literal

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, Literal["ok"]]:
    """Report that the application process is responsive."""
    return {"status": "ok"}
