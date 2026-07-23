# Milestone 1 Authentication: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

Browser retest recorded on 2026-07-16 in Chrome. Viewport: mobile 375 x 812;
other sizes were not recorded.

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
| Change password form is usable | Pass | Chrome retest confirmed the fields, validation messages, focus, and usability. |
| Temporary password forces replacement | Pass | Chrome retest confirmed forced password change for a user created through the CLI. |
| Successful password change restores access | Pass | Chrome retest confirmed the new password works, the old password fails, and password fields clear after validation errors. |
| Password change completes successfully | Pass | Chrome retest confirmed password change. |
| Authentication mobile layout at 375 x 812 | Pass | Chrome retest confirmed the authentication screens remain usable without layout issues. |

## Password Management Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Password rules | Pass | Focused tests cover incorrect current password, mismatch, minimum length, reuse, and successful replacement. |
| Forced first change | Pass | Focused tests verify the redirect, private-route blocking, allowed logout, and clearing `must_change_password`. |
| Session invalidation | Pass | Focused tests verify old sessions fail after both in-app change and CLI reset while the refreshed current session remains valid. |
| CLI password reset | Pass | Focused tests verify Argon2 replacement, forced-change state, auth-version increment, and a clear unknown-email error. |

## Additional Known Limitation (Not a Milestone 1 Gate)

`POST /logout` clears authentication state, rotates the CSRF token, and causes
subsequent requests from that browser to redirect to `/login`. A cookie copied
before logout remains cryptographically valid until its configured `Max-Age`
expires. This limitation is documented and covered by a strict `xfail`
integration test. Password changes and resets do revoke older cookies through
`auth_version`; ordinary logout does not increment that version. Full logout
replay revocation is not required by the Milestone 1 login/logout acceptance
criteria.

## Milestone 3 Browser Security Follow-up

The following browser checks remain required when the pilot domain and HTTPS
termination are available. They intentionally do not select a hosting provider
or domain.

| Manual check | Status | Expected evidence |
| --- | --- | --- |
| Every login, password, logout, Meeting, Outreach, and Weekly targets POST contains a hidden CSRF token | Pending | Browser developer tools show `csrf_token` in each submitted form. |
| A form validation error can be corrected and resubmitted | Pending | The rerendered form retains a working session-bound CSRF token. |
| Repeated failed login shows the neutral throttling message | Pending | The attempt exceeding the configured allowance returns 429 and `Retry-After`; no account-existence detail is shown. |
| Production Host allowlist accepts the selected pilot domain and rejects another Host | Pending | The configured host loads normally and an unknown Host returns 400. |
| Dashboard, charts, forms, confirmation, and mobile navigation work under CSP | Pending | Browser console has no CSP violations for required local resources or interactions. |
| Baseline security headers are present on 200, 403, 404, and Host 400 responses | Pending | Developer tools show CSP, frame denial, nosniff, referrer policy, and permissions policy. |
| HSTS remains absent until HTTPS termination is confirmed | Pending | No `Strict-Transport-Security` header is emitted before the HTTPS decision. |
