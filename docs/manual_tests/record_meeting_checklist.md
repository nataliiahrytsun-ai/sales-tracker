# Milestone 1 Record Meeting: Manual Test Checklist

Executed on 2026-07-14. Record each test as **Pass**, **Fail**, or
**Blocked**.

The available non-browser checks used a local Uvicorn server, a migrated clean
SQLite test database, and an HTTP client. The built-in browser runtime was not
started again because repeated Codex closures made browser-based checks
unreliable.

| Test | Status | Evidence |
| --- | --- | --- |
| Open Record meeting from Home | Pass | Authenticated `GET /` returned 200 and contained the `/meetings/new` action. |
| Anonymous `GET /meetings/new` redirects to `/login` | Pass | Direct HTTP request returned 303 with `Location: /login`. |
| Meeting form is usable on a desktop viewport | Blocked | Requires a visual browser check. The built-in browser runtime repeatedly closed Codex and was intentionally not restarted. Next action: repeat in a stable browser environment. |
| Meeting form is usable on a mobile-sized viewport | Blocked | Requires a visual browser check. The built-in browser runtime repeatedly closed Codex and was intentionally not restarted. Next action: repeat in a stable browser environment at a mobile-sized viewport. |
| Save a meeting using only the three required selections | Pass | HTTP submission returned 303; the saved row contained the three selections and all optional fields remained `NULL`. |
| Save all optional fields with the documented selector values | Pass | HTTP submission persisted mood, blocker, country, company, next-step date, and note with the submitted values. |
| Invalid or missing selections show clear form errors | Pass | Invalid HTTP submission returned 400 and displayed the required customer-engagement error. Automated coverage also checks all required and invalid selector errors. |
| Safe entered values remain in the form after validation failure | Pass | Company and note values remained in the returned HTML after the 400 response. |
| Successful save shows confirmation and allows another entry | Pass | Confirmation HTML contained `Meeting saved successfully` and `Record another meeting`. |
| Undo removes the meeting that was just saved | Pass | Owner `POST /meetings/{id}/undo` returned 303 and the row was absent afterward. |
| A user cannot undo another user's meeting | Pass | HTTP request against another user's seeded meeting returned 404 and did not remove it. |
| A submitted `user_id` cannot change record ownership | Pass | A forged `user_id=2` was ignored; the row was stored for the authenticated user (`user_id=1`). |

## Additional Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Apply all migrations to a clean test database | Pass | Alembic applied revisions `20260714_0001` through `20260714_0003`. No schema change was required for this task. |
| Start the application without the browser runtime | Pass | Local Uvicorn became reachable on loopback. |
| Health-check endpoint | Pass | `GET /health` returned 200. |
| Authenticated meeting form exposes the documented required options | Pass | HTTP response contained Low/Medium/High, Yes/No/Unclear, and all documented outcomes checked by the automated suite. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest`: **53 passed, 1 xfailed**. The
  expected failure documents the known inability of stateless signed-cookie
  sessions to revoke a copied pre-logout cookie.
- `.venv\Scripts\python.exe -m pytest tests\test_meetings.py -q`:
  **16 passed**.
- `.venv\Scripts\python.exe -m compileall -q app tests`: **Pass**.
- `git diff --check`: **Pass** (line-ending conversion warnings only; no
  whitespace errors).

## Unresolved Manual Checks

The two browser-dependent visual checks remain **Blocked**. Because Milestone 1
requires every manual check to pass, this record-meeting slice must not be
reported as fully manual-gate complete until desktop and mobile visual checks
can be rerun successfully in a stable browser environment.
