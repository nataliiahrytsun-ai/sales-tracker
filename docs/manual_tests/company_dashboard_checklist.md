# Milestone 2 Company Dashboard: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

The browser runtime was intentionally not started. Authentication, period
validation, aggregation, privacy, and target calculations are covered by tests.

| Test | Status | Evidence / next action |
| --- | --- | --- |
| Anonymous `/dashboard` redirects to login | Pass | Focused integration coverage verifies the private route. |
| Home retains four cards and opens Company Dashboard | Pass | Home integration coverage verifies the active `/dashboard` link. |
| Dashboard defaults to the current Monday-to-Sunday week | Pass | Deterministic coverage verifies 2026-07-13 through 2026-07-19. |
| Previous week includes both Monday and Sunday boundaries | Pass | Period and aggregate coverage verifies 2026-07-06 through 2026-07-12. |
| Current month starts on day 1 and ends today | Pass | Deterministic coverage verifies 2026-07-01 through 2026-07-15. |
| Custom range includes only its selected dates | Pass | Focused integration coverage verifies a one-day custom period. |
| Invalid and future custom dates show errors and retain input | Pass | Focused integration coverage verifies HTTP 400 and submitted values. |
| Reset returns to Current week | Pass | Focused integration coverage verifies the reset response and disabled controls. |
| Apply starts disabled and activates only for a changed valid period | Pass | Structural JavaScript coverage verifies the state calculation. |
| Six company metrics combine records from multiple users | Pass | Known fixtures verify all six totals without a user filter. |
| Empty optional counters count as zero | Pass | Current-week fixtures contain NULL counters and expected totals. |
| Current-week Company Targets sum all personal targets | Pass | Focused coverage verifies summed targets, Remaining, percentage, and capped bars. |
| Zero company target shows No company target set | Pass | Companies contacted has a zero aggregate target in focused coverage. |
| Historical periods show Actual only and explain target-history limits | Pass | Previous week and custom coverage verify the explanatory state. |
| Grouped chart keeps Outreach activities and Meetings held separate | Pass | Rendered HTML contains two adjacent series and exact accessible values. |
| Current and Previous week charts use seven daily groups | Pass | Focused service coverage verifies both Monday-to-Sunday periods. |
| Current month and Custom ranges over 14 days use calendar-week groups | Pass | Focused coverage verifies clipped Monday-to-Sunday buckets. |
| Custom ranges of 14 days or less remain grouped by day | Pass | Focused coverage verifies fourteen daily buckets. |
| Chart legend, tooltip values, and screen-reader table are present | Pass | Structural coverage verifies legend, titles, ARIA labels, and hidden exact-value table. |
| Every non-zero chart bar has its exact value above it | Pass | Rendered and structural coverage verifies both series and omits zero labels. |
| Dashboard header pairs the title with the applied period | Pass | Structural coverage verifies the shared responsive heading row. |
| Metric percentage shares the Actual/Target row, not Remaining | Pass | My Week and Dashboard structural coverage verify the common primary row. |
| Each chart value is bound to its own colored bar wrapper | Pass | Structural coverage verifies separate Outreach and Meetings bar groups. |
| Dashboard content container uses centered shared-width geometry | Pass | Structural coverage verifies width, max-width, and automatic inline margins. |
| Back to Home and the period toolbar share one desktop row | Pass | Shared report-navigation coverage verifies left navigation and right-aligned content-width toolbar. |
| Activity by day uses a compact title and explanation row | Pass | Structural coverage verifies the short muted explanation and responsive shared section heading. |
| Country totals aggregate Daily outreach country rows | Pass | Brazil aggregates rows belonging to two users. |
| Mood and blockers use only Daily outreach | Pass | Meeting-only mood/blocker fixtures do not affect Dashboard output. |
| Missing Daily outreach mood is excluded | Pass | Mood output shows only non-zero explicit categories without treating missing as Okay. |
| Employee names, company names, notes, and individual records are absent | Pass | Privacy fixtures verify foreign details are not rendered. |
| Desktop and tablet grids remain compact and readable | Blocked | Verify manually in a stable user-controlled browser. |
| Mobile uses one column without horizontal scrolling | Blocked | Verify manually around 375–376 px. |
| Long country and blocker labels wrap without clipping | Blocked | Verify manually with representative long labels. |
| Period controls and Apply/Reset states are visually clear | Blocked | Verify all preset/custom transitions manually. |
| Grouped chart labels, tooltips, and legend are readable on desktop | Blocked | Verify the chart for all four period choices. |
| Grouped chart remains readable without horizontal scroll on mobile | Blocked | Verify daily and weekly grouped ranges around 375–376 px. |
| Applied period is right-aligned beside the title on desktop/tablet | Blocked | Verify title, Back to Home, period name, and compact date alignment. |
| Header stacks in title, period, Back to Home order on mobile | Blocked | Verify around 375–376 px without horizontal scrolling. |
| Non-zero chart labels remain separated and unclipped | Blocked | Verify both sparse and dense chart ranges on desktop and mobile. |

## Unresolved Manual Checks

Desktop, tablet, and mobile visual verification remains **Blocked** because the
browser runtime was intentionally not used. Repeat the four visual checks above.
