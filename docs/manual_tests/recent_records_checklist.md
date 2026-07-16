# Milestone 1 Recent Records: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

Browser retest recorded on 2026-07-16 in Chrome.

The built-in browser runtime was not started because it is unstable in this
environment. HTTP and database behavior is covered by focused automated tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Open Meetings history from Home | Pass | View / edit meetings links directly to the private `/meetings/recent` page. |
| Open Outreach history from Home | Pass | View / edit outreach links directly to the private `/outreach/recent` page. |
| History pages do not show a Meetings / Daily outreach switch | Pass | Structural coverage verifies neither template links to the other history page. |
| Back to Home is available on both history pages | Pass | Both templates contain a clear Home link. |
| Empty history state is clear | Pass | Chrome retest confirmed the empty state on recent-record pages. |
| Default Meetings period is today plus the previous six calendar days | Pass | Focused integration coverage checks both seven-day boundaries and ownership. |
| From/To filters Meetings and allows an older range without a maximum | Pass | Focused integration coverage selects records older than 30 days. |
| Meetings are sorted newest first | Pass | Focused integration coverage verifies rendered order. |
| Apply is disabled when the rendered dates have not changed | Pass | Both pages render a native disabled Apply button; structural JavaScript coverage verifies change tracking. |
| Apply remains disabled for From later than To or future To | Pass | Client state logic checks both constraints; server integration tests independently reject both ranges. |
| Reset is disabled for the default seven-day period | Pass | Default responses render a native disabled Reset button. |
| Reset is enabled for a custom or invalid entered range | Pass | Focused integration coverage verifies the native button state. |
| Reset returns to the default seven-day period and disables both controls | Pass | Focused integration coverage requests the Reset target and verifies dates and button states. |
| From later than To shows an error and retains both values | Pass | Focused integration coverage verifies HTTP 400, the message, and retained inputs on both tabs. |
| Future To shows an error and retains both values | Pass | Focused integration coverage verifies HTTP 400, the message, and retained inputs on both tabs. |
| Edit a recent meeting and see confirmation | Pass | Focused integration coverage verifies persistence and the confirmation redirect. |
| Edit meeting clearly identifies the selected record | Pass | The edit page shows the stored meeting timestamp and company, or explicitly states that the company was not provided. Focused integration coverage checks both cases. |
| Invalid meeting edit preserves entered values | Pass | Focused integration coverage verifies the 400 response and retained safe value. |
| Delete a recent meeting requires confirmation and uses POST | Pass | The rendered action calls a confirmation dialog before submit; focused integration coverage verifies the dialog markup, POST-only deletion, and success confirmation. |
| Foreign and missing meeting IDs return 404 | Pass | GET edit, POST update, and POST delete are covered for foreign and missing IDs. |
| Anonymous users cannot call recent-record mutation routes directly | Pass | Focused integration coverage checks meeting update/delete and dated-outreach POST routes without a session. |
| Default Outreach period is today plus the previous six calendar days | Pass | Focused integration coverage checks both seven-day boundaries, sorting, and ownership. |
| From/To filters Daily outreach for the same selected period | Pass | Focused integration coverage verifies an older custom range. |
| Edit outreach by date without creating a duplicate | Pass | Focused integration coverage verifies create/update behavior and one stored row. |
| Future outreach date is rejected | Pass | Focused integration coverage verifies an HTTP 400 response and no persisted row. |
| Owned Meetings older than 30 days can be viewed, edited, and deleted | Pass | Focused integration coverage verifies all three operations while retaining ownership checks. |
| Owned Outreach older than 30 days can be viewed and edited | Pass | Focused integration coverage verifies GET and POST for an older past date. |
| Recent records desktop layout | Pass | Chrome retest confirmed the desktop layout. |
| Recent records mobile layout | Pass | Chrome retest confirmed the layout at 375 x 812. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_recent_records.py tests\test_auth.py -q --basetemp=.pytest-history`: **44 passed, 1 xfailed**.
- `python -m pytest --basetemp=C:\pytest-sales-tracker`: **109 passed, 1 xfailed**.
- The expected failure is the existing documented limitation for revoking a copied stateless signed session cookie after logout.

## Unresolved Manual Checks

No blocked manual checks remain in this checklist.
