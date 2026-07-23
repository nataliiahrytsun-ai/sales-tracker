"""Tests for release verification without external network access."""

from collections import deque
import io
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from app import release_check


class FakeResponse:
    """Minimal context-managed urllib response."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None

    def read(self, _amount: int) -> bytes:
        return self.body


class FakeOpener:
    """Deterministic opener that records requests and never uses a network."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = deque(outcomes)
        self.requests: list[tuple[Request, float]] = []

    def open(self, request: Request, *, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, FakeResponse)
        return outcome


def json_response(status: int, body: str) -> FakeResponse:
    """Build a small fake JSON response."""
    return FakeResponse(status, body.encode("utf-8"))


def successful_opener() -> FakeOpener:
    """Return exact health and readiness responses."""
    return FakeOpener(
        [
            json_response(200, '{"status":"ok"}'),
            json_response(200, '{"status":"ready"}'),
        ],
    )


def test_successful_health_and_readiness_return_success() -> None:
    """Both exact endpoint contracts produce no exception."""
    opener = successful_opener()

    release_check.verify_release(
        "http://127.0.0.1:8000",
        opener=opener,
    )

    assert [request.full_url for request, _timeout in opener.requests] == [
        "http://127.0.0.1:8000/health",
        "http://127.0.0.1:8000/ready",
    ]
    assert all(
        timeout == release_check.DEFAULT_TIMEOUT_SECONDS
        for _request, timeout in opener.requests
    )
    assert all(
        request.get_header("Cookie") is None
        and request.get_header("Authorization") is None
        for request, _timeout in opener.requests
    )


def test_main_returns_zero_and_short_success_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command exposes a conventional successful exit code."""
    monkeypatch.setattr(
        release_check,
        "verify_release",
        lambda *_args, **_kwargs: None,
    )

    exit_code = release_check.main(
        ["--base-url", "http://127.0.0.1:8000"],
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "/health" in captured.out
    assert "/ready" in captured.out
    assert captured.err == ""


def test_health_non_200_fails_without_requesting_readiness() -> None:
    """A failed liveness check stops release verification immediately."""
    private_body = "private-response-body-that-must-not-be-printed"
    error = HTTPError(
        "http://local.test/health",
        500,
        "Server Error",
        {},
        io.BytesIO(private_body.encode()),
    )
    opener = FakeOpener([error])

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/health returned HTTP 500",
    ) as raised:
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )

    assert private_body not in str(raised.value)
    assert len(opener.requests) == 1


def test_health_wrong_json_fails() -> None:
    """HTTP 200 alone is insufficient for liveness verification."""
    opener = FakeOpener([json_response(200, '{"status":"wrong"}')])

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/health returned an unexpected JSON",
    ):
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )


def test_ready_503_fails() -> None:
    """A live but unready application cannot pass release verification."""
    error = HTTPError(
        "http://local.test/ready",
        503,
        "Service Unavailable",
        {},
        io.BytesIO(b'{"status":"not_ready"}'),
    )
    opener = FakeOpener(
        [
            json_response(200, '{"status":"ok"}'),
            error,
        ],
    )

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/ready returned HTTP 503",
    ):
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )


def test_ready_wrong_json_fails() -> None:
    """Readiness must match the exact public JSON contract."""
    opener = FakeOpener(
        [
            json_response(200, '{"status":"ok"}'),
            json_response(200, '{"status":"not_ready"}'),
        ],
    )

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/ready returned an unexpected JSON",
    ):
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )


def test_network_error_is_concise() -> None:
    """Network implementation details do not enter the safe error."""
    private_detail = "private-host-or-path-detail"
    opener = FakeOpener([URLError(private_detail)])

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/health request failed",
    ) as raised:
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )

    assert private_detail not in str(raised.value)


@pytest.mark.parametrize(
    "timeout_error",
    [
        socket.timeout("private timeout detail"),
        URLError(socket.timeout("private timeout detail")),
    ],
)
def test_timeout_is_concise(timeout_error: BaseException) -> None:
    """Direct and urllib-wrapped timeouts have one safe message."""
    opener = FakeOpener([timeout_error])

    with pytest.raises(
        release_check.ReleaseCheckError,
        match=r"/health request timed out",
    ) as raised:
        release_check.verify_release(
            "http://local.test",
            opener=opener,
        )

    assert "private timeout detail" not in str(raised.value)


def test_trailing_slash_is_normalized() -> None:
    """A trailing slash never creates double-slash endpoint paths."""
    opener = successful_opener()

    release_check.verify_release(
        "https://sales.example.test/",
        opener=opener,
    )

    assert [request.full_url for request, _timeout in opener.requests] == [
        "https://sales.example.test/health",
        "https://sales.example.test/ready",
    ]


@pytest.mark.parametrize(
    "invalid_url",
    [
        "sales.example.test",
        "ftp://sales.example.test",
        "file:///tmp/application",
    ],
)
def test_non_http_urls_are_rejected(invalid_url: str) -> None:
    """Only explicit HTTP(S) origins are accepted."""
    with pytest.raises(
        release_check.ReleaseCheckError,
        match="must use http or https",
    ):
        release_check.verify_release(
            invalid_url,
            opener=FakeOpener([]),
        )


@pytest.mark.parametrize(
    ("credential_url", "private_value"),
    [
        (
            "https://private-user-marker@sales.example.test",
            "private-user-marker",
        ),
        (
            "https://account:private-password-marker@sales.example.test",
            "private-password-marker",
        ),
    ],
)
def test_urls_with_credentials_are_rejected(
    credential_url: str,
    private_value: str,
) -> None:
    """Credentials can never be embedded in or printed from the URL."""
    with pytest.raises(
        release_check.ReleaseCheckError,
        match="must not include username or password",
    ) as raised:
        release_check.verify_release(
            credential_url,
            opener=FakeOpener([]),
        )

    assert private_value not in str(raised.value)


def test_main_failure_hides_body_and_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal CLI failure prints only its safe summary."""
    private_body = "private-full-response-body"

    def fail(*_arguments: Any, **_keywords: Any) -> None:
        raise release_check.ReleaseCheckError("/ready returned HTTP 503")

    monkeypatch.setattr(release_check, "verify_release", fail)

    exit_code = release_check.main(
        ["--base-url", "http://127.0.0.1:8000"],
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "/ready returned HTTP 503" in captured.err
    assert private_body not in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_redirect_handler_never_follows_redirects() -> None:
    """Redirect targets, including external hosts, are always rejected."""
    handler = release_check.NoRedirectHandler()
    request = Request("https://sales.example.test/health")

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://external.example/collect",
    )

    assert redirected is None
