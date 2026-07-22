# Milestone 2 Company Dashboard: Manual Acceptance Test Report

## Review details

- Review date: 2026-07-20
- Reviewed viewports: 1280px, 800px, 390px, 360px
- Manual functional/UI testing status: **PASS**

## Manual functional/UI testing

| Area | Status | Manual verification |
| --- | --- | --- |
| Opening Company Dashboard | PASS | Dashboard opens from the application navigation. |
| Period, Custom range, and Users filters | PASS | Preset periods, Custom range, and user selection render and respond correctly. |
| Reset filters | PASS | Reset returns the dashboard to the default filter state. |
| Export | PASS | Export control renders and its available export actions are accessible. |
| Activity cards and progress rings | PASS | Six cards render in order: Companies contacted, Replies received, Positive replies, Meetings booked, Meetings held, Requests sent. |
| Activity trend | PASS | Activity chart, labels, and legend render. |
| Conversion section rendering | PASS | Pipeline shows High-engagement rate and Need-identification rate; Outreach shows Reply rate, Positive reply rate, and Meeting booking rate. |
| Discussion section rendering | PASS | Discussion section and its empty state render. |
| Mood summary | PASS | Mood summary, scale text, trend area, and empty state render. |
| Countries & blockers | PASS | Shared section, divider, progress bars, and empty states render. |
| Comments overview and Group by | PASS | Only Daily Outreach notes render; Meeting comments and Source are absent; Employee and Date grouping remain available. |
| Desktop navigation | PASS | Section navigation renders with active state and expected links. |
| Mobile sticky navigation and horizontal scroll | PASS | Navigation remains sticky and scrolls only inside its own container. |
| Responsive layout | PASS | Reviewed at 1280px, 800px, 390px, and 360px. |
| Page horizontal overflow | PASS | No horizontal page overflow in the reviewed layouts. |
| Main empty states and user interactions | PASS | Dashboard empty states and primary visible interactions render as expected. |
| `Edit dates` refinement | PASS | Final visual recheck: on desktop, `Edit dates` is on the same row to the right of Custom range; it is hidden outside Custom range. |
| Mobile Comments refinement | PASS | Final visual recheck: stacked records, full-width group headers and comments, and long values wrap without overflow. |

## Business logic

**Status: NOT RUN MANUALLY — covered by automated tests.**

Automated tests cover:

- the six KPI calculations and their shared order;
- Companies contacted from `DailyOutreach.unique_companies` without adding replies;
- Requests sent from current `Request sent` Meeting outcomes without legacy outcomes;
- targets and remaining values;
- previous-period ranges and comparisons;
- conversion rates and zero denominators;
- mood calculations and missing mood;
- countries, blockers, and Daily Outreach-only comments aggregation;
- filters, permissions, and CSV behavior.

## Automated verification

| Check | Status | Result |
| --- | --- | --- |
| Full suite | PASS | 241 passed, 1 expected xfailed. |
| Expected xfail | XFAIL | Signed-cookie logout replay limitation. |
| Dashboard focused tests | PASS | 78 passed. |
| `git diff --check` | PASS | No whitespace errors. |

## Final status

- Milestone 2 manual acceptance: **PASS**
- Automated regression: **PASS**
- Known expected limitation: **1 XFAIL**
- Blocking defects: **None**
