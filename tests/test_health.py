"""Tests for the health-check endpoint."""

import asyncio

import httpx

from app.main import app


def test_health_check() -> None:
    """The health-check reports a successful application response."""
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
