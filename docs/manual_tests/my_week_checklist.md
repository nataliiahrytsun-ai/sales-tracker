# Milestone 2 My Week: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

Final local browser gate recorded on 2026-07-24 with local temporary SQLite.
Authentication, ownership, week boundaries, aggregation, and progress
calculations remain covered by tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Anonymous `/my-week` redirects to login | Pass | Focused integration coverage verifies the private route. |
| Home opens My Week and retains Set weekly targets | Pass | Home integration coverage verifies both links. |
| Current week displays Monday through Sunday | Pass | Deterministic coverage verifies 2026-07-13 through 2026-07-19. |
| Companies contacted includes both week boundaries and uses `DailyOutreach.unique_companies` | Pass | Monday and Sunday fixture records are included; deliberately different legacy totals do not affect the result. |
| Records before Monday or after Sunday are excluded | Pass | Focused aggregation coverage includes both outside-boundary cases. |
| Other users' records and targets are excluded | Pass | Foreign data with deliberately large values does not affect results. |
| Empty optional outreach counters count as zero | Pass | Monday fixture leaves optional counters empty without changing totals. |
| Meetings held counts owned Meeting rows once | Pass | Focused coverage verifies two in-week meetings and excludes outside/foreign rows. |
| Requests sent counts only the current `Request sent` outcome | Pass | Focused coverage counts the current outcome and excludes a legacy Meeting outcome. |
| Existing Weekly Targets continue across later weeks | Pass | Targets with older effective dates remain active in focused coverage. |
| The six cards appear as Companies contacted, Replies received, Positive replies, Meetings booked, Meetings held, Requests sent | Pass | Rendered-order coverage verifies the shared metric contract. |
| Total outreach activities is absent | Pass | Template and rendered-page coverage verify the retired user-facing metric is not shown. |
| Actual, Target, Remaining, and percentage are correct | Pass | Focused coverage verifies all six current comparisons, including Requests sent. |
| Actual above Target shows Remaining 0 and a capped bar | Pass | Meetings held renders 200% text with a 100% bar. |
| Target 0 shows No target set without division | Pass | Neutral-state coverage verifies zero targets. |
| Progress states use orange, amber, light-green, green, and neutral styles | Pass | Unit and structural coverage verify thresholds and CSS classes. |
| Progress bars expose accessible values and labels | Pass | Template coverage verifies progressbar ARIA attributes and textual values. |
| Empty week shows a clear message and six zero metrics | Pass | Focused empty-state coverage verifies both. |
| Back to Home and Set weekly targets work | Pass | Both destinations are present in rendered HTML. |
| Current week period aligns beside My Week on desktop/tablet | Pass | Shared report-heading structural coverage verifies the title/period row and compact range. |
| Navigation has consistent space below the heading and above metrics | Pass | Shared report-navigation spacing is covered structurally; confirm visual rhythm manually. |
| Desktop/tablet card grid is readable | Pass | 2026-07-24, local temporary SQLite: 1440 x 900 and 768 x 1024 rendered all six cards in a two-column grid with no clipping or horizontal overflow. |
| Mobile cards use one column without horizontal scrolling | Pass | 2026-07-24, local temporary SQLite, 375 x 667: all six cards rendered in one column, text and values were not clipped, mobile navigation opened, and the empty state rendered without error. |

## Automated Test Record

- Focused My Week and Weekly targets tests: **18 passed**.
- Focused My Week, Weekly targets, and Dashboard regression tests: **96 passed**.
- Full test suite: **241 passed, 1 xfailed**.
- `python -m compileall app tests migrations`: **passed**.
- The expected xfail is the existing documented copied-cookie logout limitation.

## Unresolved Manual Checks

No local browser checks remain blocked in this checklist.
