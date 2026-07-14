# Milestone 1 Daily Outreach: Manual Test Checklist

Executed on 2026-07-14. Record each test as **Pass**, **Fail**, or
**Blocked**.

Available non-browser checks used a local Uvicorn server, a clean migrated
SQLite database, and a real HTTP client. The built-in browser runtime was not
started because prior visual checks repeatedly closed Codex.

| Test | Status | Evidence |
| --- | --- | --- |
| Open Update today's outreach from Home | Pass | Authenticated Home returned 200 and exposed the `/outreach/today` action; following it returned the private form. |
| Outreach form is usable on a desktop viewport | Blocked | Requires a visual browser check. Next action: repeat in a stable browser environment at a desktop viewport. |
| Outreach form is usable on a mobile-sized viewport | Blocked | Requires a visual browser check. Next action: repeat in a stable browser environment around 376 px. Structural tests cover single-column mobile grids and overflow-safe sizing. |
| Save a new outreach record | Pass | HTTP POST returned 303 and created one row for the authenticated user and application-local date. |
| Reopen and change today's record | Pass | GET reloaded stored values; a second POST updated the same row instead of creating a duplicate. |
| Validation errors are clear and preserve safe values | Pass | Invalid counters returned 400 with field errors, and the submitted note remained safely escaped in the form. |
| Successful save shows confirmation | Pass | Redirected form displayed `Today's outreach was saved.` after both create and update. |

## Additional Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| DACH country breakdown | Pass | The form and database contained only Germany/DE, Austria/AT, and Switzerland/CH. |
| Country-total mismatch | Pass | A mismatch against unique companies showed a warning and did not block saving. |
| Matching country total | Pass | Updating the breakdown to match unique companies removed the warning. |
| Forged ownership and date fields | Pass | Submitted `user_id` and `activity_date` values were ignored; ownership and date came from the authenticated session and application-local date. |
| Clean-database migrations | Pass | Existing revisions `20260714_0001` through `20260714_0003` created the required tables and unique constraint. No new migration was needed. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_outreach.py -q`:
  **10 passed**.
- `.venv\Scripts\python.exe -m pytest`: **66 passed, 1 xfailed**. The
  expected failure documents the known stateless signed-cookie logout
  limitation.
- `.venv\Scripts\python.exe -m compileall -q app tests`: **Pass**.

## Unresolved Manual Checks

Desktop and mobile visual layout checks remain **Blocked**. The daily outreach
workflow must not be reported as fully manual-gate complete until those checks
pass in a stable browser environment.
