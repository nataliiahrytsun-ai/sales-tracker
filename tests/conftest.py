"""Shared browser-test helpers."""

from collections.abc import Mapping
import re
from typing import Any

import httpx
import pytest

CSRF_INPUT_PATTERN = re.compile(
    r'name="csrf_token"\s+value="(?P<token>[^"]+)"',
)


async def csrf_token_from_browser(client: httpx.AsyncClient) -> str:
    """Read the real CSRF token from a form in the client's current session."""
    response = await client.get("/login")
    for _ in range(5):
        token_match = CSRF_INPUT_PATTERN.search(response.text)
        if token_match is not None:
            return token_match.group("token")
        if response.status_code not in {
            301,
            302,
            303,
            307,
            308,
        }:
            break
        location = response.headers.get("location")
        if not location:
            break
        response = await client.get(location)
    raise AssertionError("No CSRF-protected form was available to the client")


@pytest.fixture(autouse=True)
def submit_real_csrf_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make existing browser tests submit tokens obtained from rendered forms."""
    original_post = httpx.AsyncClient.post

    async def csrf_protected_post(
        client: httpx.AsyncClient,
        url: str,
        *,
        csrf: bool = True,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        submitted_data = dict(data or {})
        if csrf and "csrf_token" not in submitted_data:
            submitted_data["csrf_token"] = await csrf_token_from_browser(
                client,
            )
        return await original_post(
            client,
            url,
            data=submitted_data,
            **kwargs,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", csrf_protected_post)
