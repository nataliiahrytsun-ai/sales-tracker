# Milestone 1 Responsive Layout: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| `GET /login` renders the shared layout | Pass | Real Uvicorn response returned `200`, the shared stylesheet, and viewport metadata. |
| Login remains usable at a 375 x 667 viewport | Blocked | Browser runtime could not start because filesystem access to its runtime directory was denied. Retry visual inspection when the in-app browser is available. |
| Authenticated `GET /` renders shared user navigation | Pass | After login, `/` returned `200` with the user navigation and logout form. |
| Home shows the scoped actions | Pass | The rendered HTML contains Record meeting, Update today's outreach, Recent records, View this week, and Open dashboard. |
| Implemented and future actions have the correct states | Pass | Meeting, outreach, and recent-record actions navigate; only View this week and Open dashboard are disabled. |
| Logout returns the user to `/login` | Pass | `POST /logout` returned `303`, cleared the session cookie, and the next `/` request redirected to `/login`. |
| Anonymous `GET /` redirects to `/login` | Pass | Anonymous `/` returned `303` with `Location: /login`. |
| Home remains readable without horizontal scrolling at 375 x 667 | Blocked | Automated CSS checks pass, but visual viewport inspection is blocked by the unavailable browser runtime. Retry at 375 x 667 when browser access is restored. |
| Recent records screens remain readable on desktop and mobile | Blocked | Structural responsive tests cover overflow-safe cards and wrapped actions. Visual verification requires a stable user-controlled browser. |
