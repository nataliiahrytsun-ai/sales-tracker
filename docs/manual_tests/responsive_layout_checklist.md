# Milestone 1 Responsive Layout: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| `GET /login` renders the shared layout | Pass | Real Uvicorn response returned `200`, the shared stylesheet, and viewport metadata. |
| Login remains usable at a 375 x 667 viewport | Blocked | Browser runtime could not start because filesystem access to its runtime directory was denied. Retry visual inspection when the in-app browser is available. |
| Authenticated `GET /` renders shared user navigation | Pass | After login, `/` returned `200` with the user navigation and logout form. |
| Home shows exactly four primary cards | Pass | The rendered HTML contains Meeting Entry, Outreach Entry, My Week, and Dashboard, with exactly four `action-card` elements. |
| Meeting actions have the correct destinations | Pass | Record meeting links to `/meetings/new`; View / edit meetings links to the existing `/meetings/recent` workflow. |
| Outreach actions have the correct destinations | Pass | Update today’s outreach links to `/outreach/today`; View / edit outreach links to the existing `/outreach/recent` workflow. |
| Future actions have the correct states | Pass | My Week and Dashboard each show a disabled Coming soon action; no future route is exposed. |
| Home uses a 2 x 2 grid on desktop and tablet | Blocked | Structural CSS coverage verifies two equal columns from 48rem; visually check card heights and action alignment on desktop and tablet. |
| Home uses one column on mobile | Blocked | Mobile-first CSS leaves the grid at one column; visually check at 375–376 px. |
| Logout returns the user to `/login` | Pass | `POST /logout` returned `303`, cleared the session cookie, and the next `/` request redirected to `/login`. |
| Anonymous `GET /` redirects to `/login` | Pass | Anonymous `/` returned `303` with `Location: /login`. |
| Home remains readable without horizontal scrolling at 375 x 667 | Blocked | Automated CSS checks cover zero minimum widths and full-width actions, but visual viewport inspection was intentionally not run. |
| Recent records screens remain readable on desktop and mobile | Blocked | Structural responsive tests cover overflow-safe cards and wrapped actions. Visual verification requires a stable user-controlled browser. |
