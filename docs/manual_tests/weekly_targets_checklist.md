# Milestone 2 Weekly Targets: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

The browser runtime was intentionally not started. Authentication, validation,
ownership, persistence, and responsive structure are covered by automated tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Anonymous GET and POST `/targets` redirect to login | Pass | Focused integration coverage verifies both private endpoints. |
| My Week retains its disabled Coming soon action | Pass | Home integration coverage verifies the future primary action remains disabled. |
| My Week links to Set weekly targets | Pass | Home integration coverage verifies the link to `/targets`. |
| The form shows all six weekly metrics | Pass | Template and integration coverage verify the six required numeric fields. |
| The displayed week runs Monday through Sunday | Pass | Deterministic integration coverage verifies 2026-07-13 through 2026-07-19. |
| First save creates one row per metric | Pass | Focused integration coverage verifies six owned Target rows. |
| Repeated save updates without duplicates | Pass | Focused integration coverage verifies the row count remains six. |
| Zero is accepted for every metric | Pass | Focused integration coverage saves and reloads six zero values. |
| Negative, decimal, and missing values are rejected | Pass | Focused integration coverage verifies HTTP 400, field errors, and no saved rows. |
| Entered values remain after validation errors | Pass | Focused integration coverage verifies submitted values in the returned form. |
| Saved values appear when reopening the page | Pass | Focused integration coverage verifies stored values and confirmation text. |
| Users cannot see or overwrite another user's targets | Pass | Focused integration coverage verifies user-scoped reads and updates. |
| Back to Home works | Pass | The template contains the shared Home link. |
| Desktop and tablet layout is compact and readable | Blocked | Verify the two-column form and action alignment in a stable user-controlled browser. |
| Mobile layout has no horizontal scrolling | Blocked | Verify the one-column form around 375–376 px in a stable user-controlled browser. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_targets.py tests\test_auth.py tests\test_models.py tests\test_database.py -q --basetemp=.pytest-targets`: **53 passed, 1 xfailed**.
- `python -m pytest --basetemp=C:\pytest-sales-tracker`: **116 passed, 1 xfailed**.
- `.venv\Scripts\python.exe -m compileall app tests`: **passed**.
- Migration `20260715_0005 -> 20260715_0006` preserved an existing Target row and created `uq_targets_user_metric`; `alembic check`: **No new upgrade operations detected**.
- The expected xfail is the existing documented copied-cookie logout limitation.

## Unresolved Manual Checks

Desktop, tablet, and mobile visual verification remain **Blocked** because the
browser runtime was intentionally not used. Repeat these checks manually.
