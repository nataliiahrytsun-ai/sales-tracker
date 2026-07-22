# Milestone 1 Daily Outreach: Manual Test Checklist

Executed on 2026-07-14. Record each test as **Pass**, **Fail**, or
**Blocked**.

Browser retest recorded on 2026-07-16 in Chrome. Viewports: desktop (size not
recorded), tablet 768 x 1024, and mobile 375 x 667 and 375 x 812.

Available non-browser checks used a local Uvicorn server, a clean migrated
SQLite database, and a real HTTP client. The built-in browser runtime was not
started because prior visual checks repeatedly closed Codex.

| Test | Status | Evidence |
| --- | --- | --- |
| Open Update today's outreach from Home | Pass | Authenticated Home returned 200 and exposed the `/outreach/today` action; following it returned the private form. |
| Outreach form is usable on a desktop viewport | Pass | Chrome retest confirmed the desktop layout is usable. |
| Outreach form is usable on a tablet viewport | Pass | Chrome retest confirmed the layout at 768 x 1024. |
| Outreach form is usable on a mobile-sized viewport | Pass | Chrome retest confirmed the layout at 375 x 812. |
| Search finds Germany by its English name | Pass | Chrome retest confirmed search across multiple specific countries. |
| Search finds Brazil by its English name | Pass | Chrome retest confirmed search across multiple specific countries. |
| Country search | Pass | Chrome retest confirmed country search. |
| Add several arbitrary countries | Pass | Chrome retest confirmed countries can be added and removed. |
| Add the same country twice | Pass | Chrome retest confirmed a clear duplicate message, visible focus/highlight, and no duplicate row. |
| Duplicate country feedback | Pass | Chrome retest confirmed a clear message and no duplicate row. |
| Change a country count with + and − | Pass | Chrome retest confirmed decreasing from zero does not produce a negative value. |
| Plus/minus controls | Pass | Chrome retest confirmed plus/minus controls. |
| Enter an exact country count manually | Pass | Chrome retest confirmed exact manual country-count input. |
| Remove an added country | Pass | Chrome retest confirmed the country remains removed after Save and reopening Edit. |
| Remove a country in the form | Pass | Chrome retest confirmed an added country can be removed. |
| Country summaries update live | Pass | Chrome retest confirmed updates for an empty breakdown, manual count input, and adding or removing countries. |
| Companies contacted automatic total | Pass | Chrome retest confirmed Companies contacted is calculated automatically from the country counts. |
| Country summaries stay aligned | Pass | Chrome retest confirmed the country summary cards remain aligned. |
| Company-count guidance is clear | Pass | Chrome retest confirmed the complete text `Enter the number of companies contacted in each country. The total is calculated automatically.` at 375 x 667 and 375 x 812, with no old uniqueness wording, clipping, or horizontal scrolling. |
| Saved countries reappear when the record is reopened | Pass | Chrome retest confirmed saved countries appear after reopening Edit. |
| Country controls do not cause horizontal scrolling | Pass | Chrome retest confirmed a long country name causes no horizontal overflow. |
| Outreach has no horizontal overflow | Pass | Chrome retest confirmed no horizontal overflow on desktop, tablet, or at 375 x 812. |
| Save a new outreach record | Pass | HTTP POST returned 303 and created one row for the authenticated user and application-local date. |
| Reopen and change today's record | Pass | GET reloaded stored values; a second POST updated the same row instead of creating a duplicate. |
| Validation errors are clear and preserve safe values | Pass | Invalid counters returned 400 with field errors, and the submitted note remained safely escaped in the form. |
| Positive replies validation is clear | Pass | Chrome retest confirmed positive-replies validation. |
| Reply fields do not shift | Pass | Chrome retest confirmed reply fields remain stable after validation errors. |
| Successful save shows confirmation | Pass | Redirected form displayed `Today's outreach was saved.` after both create and update. |
| Country controls work with the keyboard | Pass | Chrome retest confirmed selection with Arrow Up, Arrow Down, and Enter, with visible focus/highlight. |

## Additional Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Arbitrary ISO country breakdown | Pass | Focused tests cover Brazil/BR, France/FR, Poland/PL, multiple countries, empty breakdowns, and server-side ISO validation. |
| Duplicate country protection | Pass | Server validation and the database unique constraint both reject a repeated country code for one daily record. |
| Server-derived companies contacted | Pass | Focused tests verify the saved value equals the country sum, including add/change/remove and an empty breakdown. |
| Forged legacy company-total value | Pass | A submitted legacy `unique_companies` value is ignored by the server. |
| No separate aggregate input or mismatch warning | Pass | Companies contacted is derived from the country breakdown, so the totals cannot diverge. |
| Required outreach results | Not run | Verify Replies received, Positive replies, and Meetings booked reject empty values and accept zero; covered by automated tests. |
| Added row placement and completeness | Not run | Verify added Country + Companies count rows render above Add country and incomplete rows cannot be saved; covered by automated tests. |
| Replies relationship validation | Pass | Focused tests cover positive replies below, equal to, above, and present without replies received. Invalid submissions are not saved. |
| Forged ownership and date fields | Pass | Submitted `user_id` and `activity_date` values were ignored; ownership and date came from the authenticated session and application-local date. |
| Clean-database migrations | Pass | Revisions `20260714_0001` through `20260715_0004` create the product tables and both required outreach uniqueness constraints. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_outreach.py tests\test_recent_records.py -q`:
  **29 passed**.
- `python -m pytest --basetemp=C:\pytest-sales-tracker`:
  **88 passed, 1 xfailed**. The
  expected failure documents the known stateless signed-cookie logout
  limitation.
- `.venv\Scripts\python.exe -m compileall -q app tests`: **Pass**.

## Unresolved Manual Checks

None.
