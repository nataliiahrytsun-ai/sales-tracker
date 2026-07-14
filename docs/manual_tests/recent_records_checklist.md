# Milestone 1 Recent Records: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

The built-in browser runtime was not started because it is unstable in this
environment. HTTP and database behavior is covered by focused automated tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Open Recent records from Home | Pass | Structural and integration tests verify the authenticated Home link and private recent routes. |
| Meetings list includes only the current user's last 30 calendar days | Pass | Focused integration coverage checks both window boundaries and ownership. |
| Meetings are sorted newest first | Pass | Focused integration coverage verifies rendered order. |
| Edit a recent meeting and see confirmation | Pass | Focused integration coverage verifies persistence and the confirmation redirect. |
| Invalid meeting edit preserves entered values | Pass | Focused integration coverage verifies the 400 response and retained safe value. |
| Delete a recent meeting through POST and see confirmation | Pass | Focused integration coverage verifies POST-only deletion and confirmation. |
| Foreign and missing meeting IDs return 404 | Pass | GET edit, POST update, and POST delete are covered for foreign and missing IDs. |
| Outreach list includes only the current user's last 30 calendar days | Pass | Focused integration coverage checks window boundaries, sorting, and ownership. |
| Edit outreach by date without creating a duplicate | Pass | Focused integration coverage verifies create/update behavior and one stored row. |
| Future outreach date is rejected | Pass | Focused integration coverage verifies an HTTP 400 response and no persisted row. |
| Recent records desktop layout | Blocked | Requires visual verification in a stable user-controlled browser. |
| Recent records mobile layout | Blocked | Requires visual verification around 375–376 px in a stable user-controlled browser. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_recent_records.py tests\test_meetings.py tests\test_outreach.py tests\test_auth.py --basetemp=.\.pytest_tmp`: **53 passed, 1 xfailed**.
- `.venv\Scripts\python.exe -m pytest --basetemp=.\.pytest_tmp`: **74 passed, 1 xfailed**.
- The expected failure is the existing documented limitation for revoking a copied stateless signed session cookie after logout.

## Unresolved Manual Checks

Desktop and mobile visual verification remain **Blocked**. The built-in browser
runtime was intentionally not used; repeat these checks in a stable
user-controlled browser.
