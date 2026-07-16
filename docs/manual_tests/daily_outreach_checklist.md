# Milestone 1 Daily Outreach: Manual Test Checklist

Executed on 2026-07-14. Record each test as **Pass**, **Fail**, or
**Blocked**.

Available non-browser checks used a local Uvicorn server, a clean migrated
SQLite database, and a real HTTP client. The built-in browser runtime was not
started because prior visual checks repeatedly closed Codex.

| Test | Status | Evidence |
| --- | --- | --- |
| Open Update today's outreach from Home | Pass | Authenticated Home returned 200 and exposed the `/outreach/today` action; following it returned the private form. |
| Outreach form is usable on a desktop viewport | Blocked | Requires a visual browser check. Next action: repeat in a stable browser environment at a desktop viewport. |
| Outreach form is usable on a tablet viewport | Blocked | Requires a visual browser check around the existing 48rem breakpoint. |
| Outreach form is usable on a mobile-sized viewport | Blocked | Requires a visual browser check. Next action: repeat in a stable browser environment around 376 px. Structural tests cover single-column mobile grids and overflow-safe sizing. |
| Search finds Germany by its English name | Blocked | Requires a manual browser check of the local searchable country selector. |
| Search finds Brazil by its English name | Blocked | Requires a manual browser check of the local searchable country selector. |
| Add several arbitrary countries | Blocked | Verify that only added countries appear as compact rows. |
| Add the same country twice | Blocked | Verify the inline `This country is already added` message, focus movement, and brief row highlight. |
| Change a country count with + and − | Blocked | Verify keyboard and pointer operation and that the value never goes below zero. |
| Enter an exact country count manually | Blocked | Verify non-negative whole-number input and live total refresh. |
| Remove an added country | Blocked | Verify the row disappears and remains deleted after saving. |
| Country summaries update live | Blocked | Verify Countries selected and Companies contacted update after add, remove, manual input, +, and −; an empty breakdown must show 0 for both. |
| Country summaries stay aligned | Blocked | Verify each label and value share one horizontal row, both cards match in height on desktop, and stacked mobile cards keep their internal horizontal alignment. |
| Company-count guidance is clear | Blocked | Verify `Count each company only once per day.` appears with the two compact, equally aligned summaries. |
| Saved countries reappear when the record is reopened | Blocked | Verify names and counts after create and update. |
| Country controls do not cause horizontal scrolling | Blocked | Check desktop, tablet, and mobile, including a long country name. |
| Save a new outreach record | Pass | HTTP POST returned 303 and created one row for the authenticated user and application-local date. |
| Reopen and change today's record | Pass | GET reloaded stored values; a second POST updated the same row instead of creating a duplicate. |
| Validation errors are clear and preserve safe values | Pass | Invalid counters returned 400 with field errors, and the submitted note remained safely escaped in the form. |
| Positive replies validation is clear | Blocked | Verify a missing or lower Replies received value shows `Positive replies cannot exceed replies received.` and preserves both inputs. |
| Reply fields do not shift | Blocked | Verify Replies received and Positive replies remain aligned and following fields do not jump when the reserved error row appears or clears. |
| Successful save shows confirmation | Pass | Redirected form displayed `Today's outreach was saved.` after both create and update. |

## Additional Headless Checks

| Check | Status | Evidence |
| --- | --- | --- |
| Arbitrary ISO country breakdown | Pass | Focused tests cover Brazil/BR, France/FR, Poland/PL, multiple countries, empty breakdowns, and server-side ISO validation. |
| Duplicate country protection | Pass | Server validation and the database unique constraint both reject a repeated country code for one daily record. |
| Server-derived companies contacted | Pass | Focused tests verify the saved value equals the country sum, including add/change/remove and an empty breakdown. |
| Forged legacy company-total value | Pass | A submitted legacy `unique_companies` value is ignored by the server. |
| No separate aggregate input or mismatch warning | Pass | Companies contacted is derived from the country breakdown, so the totals cannot diverge. |
| Replies relationship validation | Pass | Focused tests cover positive replies below, equal to, above, and present without replies received. Invalid submissions are not saved. |
| Forged ownership and date fields | Pass | Submitted `user_id` and `activity_date` values were ignored; ownership and date came from the authenticated session and application-local date. |
| Clean-database migrations | Pass | Revisions `20260714_0001` through `20260715_0004` create the product tables and both required outreach uniqueness constraints. |

## Automated Test Record

- `.venv\Scripts\python.exe -m pytest tests\test_outreach.py tests\test_recent_records.py -q`:
  **29 passed**.
- `python -m pytest --basetemp=C:\pytest-sales-tracker`:
  **88 passed, 1 xfailed**. The
  expected failure documents the known stateless signed-cookie logout
  limitation.
- `.venv\Scripts\python.exe -m compileall -q app tests`: **Pass**.

## Unresolved Manual Checks

Desktop and mobile visual layout checks remain **Blocked**. The daily outreach
workflow must not be reported as fully manual-gate complete until those checks
pass in a stable browser environment.
