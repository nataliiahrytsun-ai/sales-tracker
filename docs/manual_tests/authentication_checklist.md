# Milestone 1 Authentication: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Login succeeds with a valid active user | Pass | Real Uvicorn server returned `303` to `/`, then authenticated `/` returned `200`. |
| Login fails with an incorrect password | Pass | Login returned `401` and did not create a session. |
| Login fails for an inactive user | Pass | Login returned `401` and did not create a session. |
| Anonymous access to `/` redirects to `/login` | Pass | Anonymous request returned `303` with `Location: /login`. |
| Authenticated access to `/` succeeds | Pass | Request using the login session returned `200`. |
| Logout clears the session and protects `/` again | Pass | Logout returned `303`; the next request to `/` returned `303` to `/login`. |
| Session cookie contains the `HttpOnly` flag | Pass | Login response `Set-Cookie` header contained `HttpOnly`. |
| Session cookie has a finite lifetime | Pass | Login response contains the configured `Max-Age`; the default is 1,209,600 seconds (14 days). |
| Stored password value is a hash and not plaintext | Pass | Stored value used the Argon2 format and differed from the test password. |
| Insecure production session configuration fails clearly | Pass | Startup rejected both a missing secret and `SALES_TRACKER_SESSION_COOKIE_SECURE=false`, naming the relevant environment variable. |
| A copied pre-logout cookie is rejected by the server | Blocked | Known limitation: stateless signed cookies cannot be revoked server-side; the strict replay test remains `xfail` until the session architecture changes. |

## Known limitation

`POST /logout` expires the browser's session cookie and subsequent requests from
that browser are redirected to `/login`. A cookie copied before logout remains
cryptographically valid until its configured `Max-Age` expires. This limitation
is documented and covered by a strict `xfail` integration test.
