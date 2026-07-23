"""Verify the health and readiness of an already running release."""

import argparse
from collections.abc import Sequence
import json
import math
import socket
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 4096


class ReleaseCheckError(RuntimeError):
    """A safe, concise release verification failure."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so verification never changes hosts."""

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


def normalize_base_url(raw_url: str) -> str:
    """Validate and normalize an HTTP(S) application origin."""
    candidate = raw_url.strip()
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
    except (UnicodeError, ValueError) as error:
        raise ReleaseCheckError(
            "--base-url is not a valid URL",
        ) from error
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ReleaseCheckError(
            "--base-url must use http or https",
        )
    if not parsed.netloc or hostname is None:
        raise ReleaseCheckError("--base-url must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ReleaseCheckError(
            "--base-url must not include username or password",
        )
    try:
        parsed.port
    except ValueError as error:
        raise ReleaseCheckError(
            "--base-url contains an invalid port",
        ) from error
    if parsed.query or parsed.fragment:
        raise ReleaseCheckError(
            "--base-url must not include a query or fragment",
        )
    if parsed.path not in {"", "/"}:
        raise ReleaseCheckError(
            "--base-url must not include an application path",
        )
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            "",
            "",
            "",
        ),
    )


def _request_json(
    opener: Any,
    url: str,
    *,
    endpoint_name: str,
    timeout_seconds: float,
) -> object:
    """Request bounded JSON without cookies, auth, or redirect following."""
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "sales-tracker-release-check",
        },
    )
    try:
        with opener.open(
            request,
            timeout=timeout_seconds,
        ) as response:
            if response.status != 200:
                raise ReleaseCheckError(
                    f"{endpoint_name} returned HTTP {response.status}",
                )
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except ReleaseCheckError:
        raise
    except HTTPError as error:
        raise ReleaseCheckError(
            f"{endpoint_name} returned HTTP {error.code}",
        ) from error
    except (socket.timeout, TimeoutError) as error:
        raise ReleaseCheckError(
            f"{endpoint_name} request timed out",
        ) from error
    except URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise ReleaseCheckError(
                f"{endpoint_name} request timed out",
            ) from error
        raise ReleaseCheckError(
            f"{endpoint_name} request failed",
        ) from error
    except OSError as error:
        raise ReleaseCheckError(
            f"{endpoint_name} request failed",
        ) from error

    if len(body) > MAX_RESPONSE_BYTES:
        raise ReleaseCheckError(
            f"{endpoint_name} returned an oversized response",
        )
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseCheckError(
            f"{endpoint_name} returned invalid JSON",
        ) from error


def verify_release(
    base_url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    opener: Any | None = None,
) -> None:
    """Require the exact public liveness and readiness contracts."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ReleaseCheckError(
            "--timeout-seconds must be greater than zero",
        )
    normalized_url = normalize_base_url(base_url)
    selected_opener = opener or build_opener(NoRedirectHandler())

    health = _request_json(
        selected_opener,
        f"{normalized_url}/health",
        endpoint_name="/health",
        timeout_seconds=timeout_seconds,
    )
    if health != {"status": "ok"}:
        raise ReleaseCheckError(
            "/health returned an unexpected JSON response",
        )

    readiness = _request_json(
        selected_opener,
        f"{normalized_url}/ready",
        endpoint_name="/ready",
        timeout_seconds=timeout_seconds,
    )
    if readiness != {"status": "ready"}:
        raise ReleaseCheckError(
            "/ready returned an unexpected JSON response",
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the release-check command parser."""
    parser = argparse.ArgumentParser(prog="python -m app.release_check")
    parser.add_argument(
        "--base-url",
        required=True,
        help="HTTP(S) origin of the already running application.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-request timeout in seconds (default: 5).",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run release verification with safe output and exit codes."""
    parsed = build_parser().parse_args(arguments)
    try:
        verify_release(
            parsed.base_url,
            timeout_seconds=parsed.timeout_seconds,
        )
    except ReleaseCheckError as error:
        print(f"Release check failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Release check failed: unexpected verification error",
            file=sys.stderr,
        )
        return 1
    print("Release check passed: /health and /ready returned expected results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
