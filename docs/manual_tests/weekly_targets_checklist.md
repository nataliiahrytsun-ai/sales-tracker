# Milestone 2 Weekly Targets: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

The browser runtime was intentionally not started. Authentication, validation,
ownership, persistence, and responsive structure are covered by automated tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Anonymous GET and POST `/targets` redirect to login | Pass | Focused integration coverage verifies both private endpoints. |
| Home opens My Week and My Week links to Set weekly targets | Pass | Integration coverage verifies both routes and links. |
| The form shows Companies contacted, Replies received, Positive replies, Meetings booked, Meetings held, Requests sent in this order | Pass | Template and integration coverage verify the shared six-field contract. |
| Total outreach activities is absent | Pass | The route, form values, template, and persisted current metric set exclude it. |
| The displayed week runs Monday through Sunday | Pass | Deterministic integration coverage verifies 2026-07-13 through 2026-07-19. |
| First save creates one row per metric | Pass | Focused integration coverage verifies six owned Target rows. |
| Repeated save updates without duplicates | Pass | Focused integration coverage verifies the row count remains six. |
| Zero is accepted for every metric | Pass | Focused integration coverage saves and reloads six zero values. |
| Negative, decimal, and missing values are rejected | Pass | Focused integration coverage verifies HTTP 400, field errors, and no saved rows. |
| Entered values remain after validation errors | Pass | Focused integration coverage verifies submitted values in the returned form. |
| Saved values appear when reopening the page | Pass | Focused integration coverage verifies stored values and confirmation text. |
| Requests sent saves and reloads | Pass | Repeated-save coverage verifies its persisted value after reopening the page. |
| Users cannot see or overwrite another user's targets | Pass | Focused integration coverage verifies user-scoped reads and updates. |
| Back to Home works | Pass | The template contains the shared Home link. |
| Current week period aligns beside Weekly targets on desktop/tablet | Pass | Shared report-heading structural coverage verifies the compact title/period row. |
| Header, navigation, and form use the shared report spacing | Pass | Shared report-navigation spacing is covered structurally; confirm visual rhythm manually. |
| Desktop and tablet layout is compact and readable | Blocked | Verify the two-column form and action alignment in a stable user-controlled browser. |
| Mobile layout has no horizontal scrolling | Blocked | Verify the one-column form around 375–376 px in a stable user-controlled browser. |

## Automated Test Record

- Focused My Week and Weekly targets tests: **18 passed**.
- Focused My Week, Weekly targets, and Dashboard regression tests: **96 passed**.
- Full test suite: **241 passed, 1 xfailed**.
- `python -m compileall app tests migrations`: **passed**.
- No migration was created for the six-metric alignment. Historical `total_activities` fields and target rows remain available only for technical compatibility.
- The expected xfail is the existing documented copied-cookie logout limitation.

## Unresolved Manual Checks

Desktop, tablet, and mobile visual verification remain **Blocked** because the
browser runtime was intentionally not used. Repeat these checks manually.
