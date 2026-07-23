"""Browser request security and pilot login throttling."""

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from math import ceil
import secrets
from threading import Lock
import time

from fastapi import HTTPException, Request, status
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_ERROR_MESSAGE = "Request could not be validated."

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ),
)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    ),
    "content-security-policy": CONTENT_SECURITY_POLICY,
}


def get_or_create_csrf_token(request: Request) -> str:
    """Return the session CSRF token, creating a strong token if necessary."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def reset_session(request: Request) -> str:
    """Clear session state and immediately rotate its CSRF token."""
    request.session.clear()
    return get_or_create_csrf_token(request)


async def enforce_csrf(request: Request) -> None:
    """Require a session-bound token for every state-changing browser request."""
    expected_token = get_or_create_csrf_token(request)
    if request.method.upper() not in STATE_CHANGING_METHODS:
        return

    supplied_token = request.headers.get(CSRF_HEADER, "")
    if not supplied_token:
        form = await request.form()
        form_token = form.get(CSRF_FORM_FIELD, "")
        supplied_token = form_token if isinstance(form_token, str) else ""
    if not supplied_token or not compare_digest(
        supplied_token,
        expected_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=CSRF_ERROR_MESSAGE,
        )


class SecurityHeadersMiddleware:
    """Add baseline browser security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


@dataclass(frozen=True)
class LoginRateLimitKey:
    """A privacy-minimal login limiter bucket."""

    client_host: str
    identifier: str


class LoginRateLimiter:
    """Single-process failed-login limiter for the pilot deployment."""

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.clock = clock
        self._failures: defaultdict[
            LoginRateLimitKey,
            deque[float],
        ] = defaultdict(deque)
        self._blocked_until: dict[LoginRateLimitKey, float] = {}
        self._lock = Lock()

    @staticmethod
    def key(request: Request, identifier: str) -> LoginRateLimitKey:
        """Combine the direct peer IP and normalized login identifier."""
        client_host = (
            request.client.host
            if request.client is not None and request.client.host
            else "unknown"
        )
        return LoginRateLimitKey(
            client_host=client_host,
            identifier=identifier.strip().casefold(),
        )

    def retry_after(self, key: LoginRateLimitKey) -> int | None:
        """Return remaining block seconds, or None when the key may try."""
        now = self.clock()
        with self._lock:
            blocked_until = self._blocked_until.get(key)
            if blocked_until is None:
                return None
            if blocked_until <= now:
                self._blocked_until.pop(key, None)
                self._failures.pop(key, None)
                return None
            return max(1, ceil(blocked_until - now))

    def record_failure(self, key: LoginRateLimitKey) -> int | None:
        """Record one failed authentication and block after allowed attempts."""
        now = self.clock()
        with self._lock:
            failures = self._failures[key]
            window_start = now - self.window_seconds
            while failures and failures[0] <= window_start:
                failures.popleft()
            failures.append(now)
            if len(failures) <= self.max_attempts:
                return None
            blocked_until = now + self.block_seconds
            self._blocked_until[key] = blocked_until
            return self.block_seconds

    def clear(self, key: LoginRateLimitKey) -> None:
        """Clear failed-attempt state after a successful authentication."""
        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def clear_all(self) -> None:
        """Clear all state for deterministic tests and controlled maintenance."""
        with self._lock:
            self._failures.clear()
            self._blocked_until.clear()
