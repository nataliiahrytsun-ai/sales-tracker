# Milestone 2 Weekly Targets: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

Final local browser gate recorded on 2026-07-24 with local temporary SQLite.
Authentication, ownership, and persistence remain covered by automated tests.

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
| Desktop and tablet layout is compact and readable | Pass | 2026-07-24, local temporary SQLite: 1440 x 900 and 768 x 1024 rendered the six targets in the documented order and a two-column grid without clipping or horizontal overflow. |
| Mobile layout has no horizontal scrolling | Pass | 2026-07-24, local temporary SQLite, 375 x 667: the form became one column with no clipping or horizontal overflow; native negative-value validation was clear, correction saved, and all six values reloaded. |

## Automated Test Record

- Focused My Week and Weekly targets tests: **18 passed**.
- Focused My Week, Weekly targets, and Dashboard regression tests: **96 passed**.
- Full test suite: **241 passed, 1 xfailed**.
- `python -m compileall app tests migrations`: **passed**.
- No migration was created for the six-metric alignment. Historical `total_activities` fields and target rows remain available only for technical compatibility.
- The expected xfail is the existing documented copied-cookie logout limitation.

## Unresolved Manual Checks

No local browser checks remain blocked in this checklist.
