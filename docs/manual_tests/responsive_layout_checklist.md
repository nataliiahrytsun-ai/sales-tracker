# Milestone 1 Responsive Layout: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| `GET /login` renders the shared layout | Pass | Real Uvicorn response returned `200`, the shared stylesheet, and viewport metadata. |
| Login remains usable at a 375 x 667 viewport | Blocked | Browser runtime could not start because filesystem access to its runtime directory was denied. Retry visual inspection when the in-app browser is available. |
| Authenticated `GET /` renders shared user navigation | Pass | After login, `/` returned `200` with the user navigation and logout form. |
| Home shows exactly the four specified actions | Pass | The rendered HTML contains all four specified actions and no additional action cards. |
| Unimplemented actions are disabled and do not navigate | Pass | All four controls have `disabled`; no future meeting, outreach, or dashboard URL is rendered. |
| Logout returns the user to `/login` | Pass | `POST /logout` returned `303`, cleared the session cookie, and the next `/` request redirected to `/login`. |
| Anonymous `GET /` redirects to `/login` | Pass | Anonymous `/` returned `303` with `Location: /login`. |
| Home remains readable without horizontal scrolling at 375 x 667 | Blocked | Automated CSS checks pass, but visual viewport inspection is blocked by the unavailable browser runtime. Retry at 375 x 667 when browser access is restored. |
