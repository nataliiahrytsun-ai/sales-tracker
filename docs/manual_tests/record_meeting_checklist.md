# Milestone 1 Record Meeting: Manual Test Checklist

Executed on 2026-07-14. Record each test as **Pass**, **Fail**, or
**Blocked**.

Browser retest recorded on 2026-07-16 in Chrome. Viewports: desktop (size not
recorded) and mobile 375 x 812.

Final local browser gate recorded on 2026-07-24 with local temporary SQLite.

| Test | Status | Evidence |
| --- | --- | --- |
| Open Record meeting from Home | Pass | Authenticated `GET /` returned 200 and contained the `/meetings/new` action. |
| Anonymous `GET /meetings/new` redirects to `/login` | Pass | Direct HTTP request returned 303 with `Location: /login`. |
| Meeting form is usable on a desktop viewport | Pass | Chrome retest confirmed the desktop layout is usable. |
| Meeting form is usable on a mobile-sized viewport | Pass | Chrome retest confirmed the layout is usable at 375 x 812. |
| Save a meeting using Company plus the three required selections | Pass | 2026-07-24, local temporary SQLite, 1440 x 900: whitespace-only Company returned HTTP 400, correction with Company plus the three selections returned 303 and displayed the success confirmation. The former wording that Company was optional is superseded. |
| Historical optional-field verification | Pass | Superseded / verified by current code and tests. The 2026-07-14 evidence covered a former form shape; current Meeting Company is required, while historical rows with missing Company remain readable. |
| Search and select a country by English name | Pass | Chrome retest confirmed Brazil and Poland are found with the correct display names. |
| Country search and selection | Pass | Chrome retest confirmed country search and selection. |
| Selected country survives errors and editing | Pass | Chrome retest confirmed the selected country remains after a validation error and displays correctly when Edit is reopened. |
| Invalid or missing selections show clear form errors | Pass | Invalid HTTP submission returned 400 and displayed the required customer-engagement error. Automated coverage also checks all required and invalid selector errors. |
| Safe entered values remain in the form after validation failure | Pass | Company and note values remained in the returned HTML after the 400 response. |
| Successful save shows confirmation and allows another entry | Pass | Confirmation HTML contained `Meeting saved successfully` and `Record another meeting`. |
| Undo removes the meeting that was just saved | Pass | Owner `POST /meetings/{id}/undo` returned 303 and the row was absent afterward. |
| A user cannot undo another user's meeting | Pass | HTTP request against another user's seeded meeting returned 404 and did not remove it. |
| A submitted `user_id` cannot change record ownership | Pass | A forged `user_id=2` was ignored; the row was stored for the authenticated user (`user_id=1`). |
| Meeting form has no horizontal overflow | Pass | Chrome retest confirmed no horizontal overflow at 375 x 812. |

## Additional Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Apply all migrations to a clean test database | Pass | 2026-07-24, local temporary SQLite: Alembic applied revisions `20260714_0001` through current head `20260721_0008`. The earlier `0003` result remains historical evidence. |
| Start the application without the browser runtime | Pass | Local Uvicorn became reachable on loopback. |
| Health-check endpoint | Pass | `GET /health` returned 200. |
| Authenticated meeting form exposes the documented required options | Pass | HTTP response contained Low/Medium/High, Yes/No/Unclear, and all documented outcomes checked by the automated suite. |
| Worldwide country validation | Pass | Automated tests cover Brazil, Poland, empty country as `NULL`, rejection of an unknown code, error re-rendering, and Edit meeting display. |
| Current Meeting taxonomy | Pass | Superseded / verified by current code and tests on 2026-07-24: Company is required on create and edit; the five outcomes are Waiting for further information, No outcome, Request sent, Manual alignment (discussion), and Unclear; historical missing-Company and legacy-outcome rows open safely. |

## Automated Test Record

- Current full-suite control, 2026-07-24: **364 passed, 1 xfailed** using
  local temporary storage. The expected xfail is the documented stateless
  signed-cookie replay limitation.
- The results below are retained as historical verification records.
- `python -m pytest --basetemp=C:\pytest-sales-tracker`: **90 passed, 1 xfailed**. The
  expected failure documents the known inability of stateless signed-cookie
  sessions to revoke a copied pre-logout cookie.
- `.venv\Scripts\python.exe -m pytest tests\test_meetings.py tests\test_recent_records.py -q`:
  **30 passed**.
- `.venv\Scripts\python.exe -m compileall -q app tests`: **Pass**.
- `git diff --check`: **Pass** (line-ending conversion warnings only; no
  whitespace errors).

## Unresolved Manual Checks

No blocked manual checks remain in this checklist.
