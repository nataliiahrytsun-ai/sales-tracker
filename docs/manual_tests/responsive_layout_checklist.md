# Milestone 1 Responsive Layout: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

Browser retest recorded on 2026-07-16 in Chrome. Viewports: 375 x 667,
375 x 812, and desktop and tablet sizes that were not recorded.

| Test | Status | Evidence |
| --- | --- | --- |
| `GET /login` renders the shared layout | Pass | Real Uvicorn response returned `200`, the shared stylesheet, and viewport metadata. |
| Login remains usable at a 375 x 667 viewport | Pass | Chrome retest confirmed the login layout at 375 x 667. |
| Login remains usable at a 375 x 812 viewport | Pass | Chrome retest confirmed the mobile authentication layout. |
| Authenticated `GET /` renders shared user navigation | Pass | After login, `/` returned `200` with the user navigation and logout form. |
| Home shows exactly four primary cards | Pass | The rendered HTML contains Meeting Entry, Outreach Entry, My Week, and Dashboard, with exactly four `action-card` elements. |
| Meeting actions have the correct destinations | Pass | Record meeting links to `/meetings/new`; View / edit meetings links to the existing `/meetings/recent` workflow. |
| Outreach actions have the correct destinations | Pass | Update today’s outreach links to `/outreach/today`; View / edit outreach links to the existing `/outreach/recent` workflow. |
| Reporting actions have the correct destinations | Pass | My Week and Dashboard are available application actions and open their implemented routes. |
| Home uses a 2 x 2 grid on desktop and tablet | Pass | Chrome retest confirmed the 2 x 2 grid on desktop and tablet. |
| Home uses one column on mobile | Pass | Chrome retest confirmed the Home layout at 375 x 812. |
| Logout returns the user to `/login` | Pass | `POST /logout` returned `303`, cleared the session cookie, and the next `/` request redirected to `/login`. |
| Anonymous `GET /` redirects to `/login` | Pass | Anonymous `/` returned `303` with `Location: /login`. |
| Home remains readable without horizontal scrolling at 375 x 667 | Pass | Chrome retest confirmed no horizontal scrolling at 375 x 667. |
| Home remains readable without horizontal scrolling at 375 x 812 | Pass | Chrome retest confirmed no horizontal scrolling. |
| Recent records screens remain readable on desktop and mobile | Pass | Chrome retest confirmed both desktop and 375 x 812 layouts. |
