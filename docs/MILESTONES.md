# Milestone 1 — Foundation and Data Entry

## Goal

Create the working application foundation and allow users to record and edit sales activity.

## Scope

* Create the FastAPI project structure
* Configure SQLite, SQLModel, and Alembic
* Enable SQLite foreign keys and Write-Ahead Logging
* Implement authentication
* Implement a single authenticated user type with equal permissions
* Create the responsive base layout
* Implement pipeline meeting entry
* Implement daily outreach entry
* Implement country breakdown for outreach
* Enforce one outreach record per user and date
* Add editing and deletion of recent records
* Add validation, warnings, confirmation, and Undo behavior
* Add automated tests for authentication, forms, validation, and database constraints

## Deliverable

An authenticated user can:

* record a pipeline meeting;
* save a meeting without optional fields;
* create or update today’s outreach summary;
* edit or delete recent entries;
* use the application on desktop and mobile.

## Acceptance Criteria

* Meeting entry supports the three required selections
* Outreach entry supports counters and company counts by country
* Companies contacted is calculated automatically as the sum of country company counts and is not entered separately
* Country rows are optional; added rows require a country and a non-negative whole-number company count
* Replies received, positive replies, and meetings booked from outreach are required
* The application does not collect company names or identifiers for outreach and does not verify uniqueness or perform deduplication
* The internal `unique_companies` field may be retained for backward compatibility; its user-facing meaning is the automatically calculated Companies contacted metric
* Only one outreach record exists per user and date
* Missing mood remains empty
* Data is stored correctly and protected by authorization checks

## Unit Test Gate

- All unit tests related to this milestone must pass.
- Run the complete available unit test suite before marking the milestone complete.
- Record the commands executed and the test results.
- Do not mark the milestone complete while required unit tests are failing.

## Manual Test Gate

Complete and document the manual test checklist for this milestone.

Record each test as:

- Pass
- Fail
- Blocked

### Manual Test Checklist
  
- Application starts successfully using the documented command.
- Health-check endpoint returns a successful response.
- Login and logout work.
- Unauthorized users cannot access protected pages.
- A pipeline meeting can be created using only the required fields.
- A saved meeting is visible in recent entries.
- A recent meeting can be edited and deleted.
- Today's outreach record can be created.
- Today's outreach record can be updated without creating a duplicate.
- Companies contacted equals the sum of the submitted country company counts and is not entered separately.
- Optional mood, blocker, meeting company/country, next-step date, outreach country rows, and note fields may be empty.
- Main data-entry screens are usable on a mobile-sized viewport.
  
The milestone is complete only when all required unit tests pass and all manual tests are recorded as Pass.

Any Fail or Blocked result must be documented with the reason and next action.

---

# Milestone 2 — Dashboard, Metrics, and Export

## Goal

Provide authenticated users with a usable weekly view of activity, outcomes, sentiment, and blockers.

## Scope

* Implement the dashboard
* Open the current week by default
* Add date-range filters
* Add user filters
* Add pipeline activity and conversion metrics
* Add outreach metrics and rates
* Add activity compared with targets
* Add country breakdown
* Add sentiment average and distribution
* Add mood trends and blocker summaries
* Add non-punitive Discussion prompts
* Add pipeline and outreach CSV exports
* Add tests for filters, calculations, empty data, division by zero, and permissions

## Deliverable

Authenticated users can review the current week, filter results, compare activity and outcomes, inspect sentiment and blockers, and export data.

## Acceptance Criteria

- The dashboard opens on the current week by default.
- Date filters support current week, last week, current month, and a custom date range.
- Data can be filtered by all users or an individual user.
- Activity, customer response, progress, and sentiment are displayed separately.
- Pipeline metrics use the definitions from the Implementation Plan.
- Outreach rates use the formulas from the Implementation Plan.
- Missing data, empty values, and zero denominators are handled safely.
- Companies contacted by country are visible.
- Mood average and distribution are both visible.
- Missing mood is excluded from sentiment calculations and is not treated as neutral.
- Previous-period comparisons follow the exact range, metric, formatting, missing-data, chart, and accessibility rules in `docs/implementation-plan.md`.
- The previous range is resolved by the documented rules and its actual dates are visible to the user.
- Current week is compared with the same elapsed weekdays of the previous week, not a complete previous week.
- Last week is compared with the complete week immediately before it.
- Current month is compared with the corresponding calendar days of the previous month without duplicating a shortened month's final day.
- A custom range is compared with the immediately preceding, non-overlapping range of the same inclusive duration.
- The same All-users or individual-user filter is applied to both periods and both mood-chart series.
- Quantitative metrics show the absolute difference, not relative percentage growth.
- Conversion rates show the percentage-point difference, not relative percentage change.
- Average mood shows the numerical difference using the current Mood summary rounding, without treating missing mood as `Okay`.
- Zero denominators and unavailable previous-period data produce the documented neutral states without `NaN`, `Infinity`, division errors, or misleading values.
- Positive differences use a green upward arrow and signed value; negative differences use a red downward arrow and signed value; no change and unavailable comparisons use neutral styling.
- Comparison direction and meaning remain understandable without relying on color alone.
- The Dashboard displays `Mood scale: 1 = Difficult · 2 = Okay · 3 = Good`.
- `Daily mood trend` shows `Selected period` as a solid line and available `Previous period` data as a green dashed line.
- The mood-chart legend names both series, and the dashed style distinguishes the previous period independently of color.
- Mood-chart points are paired by ordinal day position within their ranges rather than by equal calendar date.
- Mood-chart tooltips show the actual period, date, and value for both series.
- Missing daily mood values remain missing and create series gaps where supported; a completely unavailable previous series is omitted with `No previous mood data`.
- Previous-period comparison labels and the two-series mood chart remain usable without horizontal overflow on mobile.
- Common blockers are visible.
- Discussion prompts are implemented according to `docs/implementation-plan.md`.
- Discussion prompt calculations respect the selected date and user filters.
- All triggered Discussion prompt types are displayed in the fixed priority order from `docs/implementation-plan.md`.
- Discussion prompts use neutral, non-punitive wording.
- The neutral empty state is displayed when no Discussion prompt rule triggers.
- Pipeline and outreach data can be exported to CSV.
- Dashboard and export access is protected by authentication and authorization.
- Sentiment data is available only to authenticated users, with the same visibility rules for every user.

## Unit Test Gate

- All unit tests related to this milestone must pass.
- Run the complete available unit test suite before marking the milestone complete.
- Test metric calculations using known input data and expected results.
- Test empty datasets, missing values, and zero denominators.
- Test date and user filters.
- Test CSV export content and access control.
- Record the commands executed and the test results.
- Do not mark the milestone complete while required unit tests are failing.

## Manual Test Gate

Complete and document the following manual test checklist.

Record each test with one of these statuses:

- Pass
- Fail
- Blocked

### Manual Test Checklist

- Dashboard opens on the current week without requiring a filter selection.
- This week filter displays the expected records.
- Last week filter displays the expected records.
- This month filter displays the expected records.
- Custom date range displays only records inside the selected range.
- All-users filter displays combined data.
- Individual-user filter displays only the selected user's data.
- Current-week comparisons use the same elapsed weekdays from the previous week.
- Last-week comparisons use the complete week immediately before last week.
- Current-month comparisons use the corresponding previous-month dates.
- A current-month comparison across months of different lengths uses each existing previous-month date once, shows the actual shorter range, and creates no duplicate days.
- A custom-range comparison uses the immediately preceding, non-overlapping range with the same inclusive calendar-day duration.
- The displayed `Compared with ...` label contains the actual resolved previous-period dates.
- All-users comparisons use combined All-users data for both periods.
- An individual-user comparison and both mood-chart series exclude every other user's data.
- A positive difference shows the correct absolute or percentage-point value with a green upward arrow, `+` sign, and descriptive text.
- A negative difference shows the correct absolute or percentage-point value with a red downward arrow, `−` sign, and descriptive text.
- An unchanged metric displays the neutral `No change` state.
- Comparison direction remains understandable when color is unavailable.
- A previous conversion denominator of zero displays `No comparable previous rate` without `NaN`, `Infinity`, or an error.
- A missing previous-period Average mood displays `No previous mood data` and is not treated as `Okay`.
- An empty current period retains safe empty-data behavior without a fabricated numerical difference.
- The Dashboard displays the exact text `Mood scale: 1 = Difficult · 2 = Okay · 3 = Good`.
- `Daily mood trend` with two complete series shows a solid `Selected period` line and a green dashed `Previous period` line.
- `Daily mood trend` with partially missing values preserves gaps and displays the remaining available points without substituting `Okay`.
- `Daily mood trend` without previous-period mood data omits the empty dashed line and displays `No previous mood data`.
- The two mood series match points by ordinal day position, including weekday-to-weekday and custom-range comparisons.
- Mood-chart tooltips show the actual dates and values for both `Selected period` and `Previous period`.
- The mood-chart legend clearly names both series and remains readable when wrapped.
- Previous-period comparison labels and the two-series mood chart remain readable on mobile without clipped content or horizontal page scrolling.
- Pipeline meeting totals match manually prepared test records.
- High-engagement rate matches a manual calculation.
- Need-identification rate matches a manual calculation.
- Concrete-next-step rate uses only the outcomes defined in the Implementation Plan.
- Proposal and opportunity rates match manually prepared test records.
- Outreach reply rate matches a manual calculation.
- Positive reply rate matches a manual calculation.
- Outreach meeting booking rate matches a manual calculation.
- Dashboard loads without errors when no records exist for the selected period.
- Dashboard loads without errors when a rate denominator is zero.
- Country breakdown shows the correct activity and results.
- Mood average matches manually prepared mood data.
- Mood distribution shows the correct Difficult, Okay, and Good counts.
- Records with missing mood are not included as Okay or another neutral value.
- Common blockers are displayed with correct counts.
- Consecutive difficult days triggers according to the exact rule in `docs/implementation-plan.md`.
- Few concrete next steps triggers according to the exact rule in `docs/implementation-plan.md`.
- Positive replies without booked meetings triggers according to the exact rule in `docs/implementation-plan.md`.
- Repeated blocker triggers and applies its deterministic selection and tie-break rules according to `docs/implementation-plan.md`.
- Every Discussion prompt threshold is tested immediately below, at, and, where applicable, above its boundary.
- Discussion prompt calculations include only data inside the selected date range.
- Discussion prompt calculations for an individual user include only that user's data.
- Discussion prompt calculations for All users use the combined filtered data.
- Qualifying Discussion prompts follow the fixed priority order in `docs/implementation-plan.md`.
- All four Discussion prompt cards are displayed when all four rules qualify, in the documented fixed priority order.
- No duplicate Discussion prompt types are displayed.
- The neutral empty state is displayed when no rule triggers.
- Discussion prompts use neutral, non-punitive wording and do not use warning styling or accusatory language.
- Pipeline CSV export downloads successfully.
- Pipeline CSV contains the expected records and fields.
- Outreach CSV export downloads successfully.
- Outreach CSV contains the expected records and country data.
- Unauthorized users cannot access the dashboard.
- Unauthorized users cannot access export routes.
- Sentiment information is unavailable to unauthenticated users and follows the same rules for every authenticated user.
- Dashboard remains usable on a mobile-sized viewport.

The milestone is complete only when all required unit tests pass and all manual tests are recorded as Pass.

Any Fail or Blocked result must be documented with the reason and next action.

---

# Milestone 3 — Quality, Deployment, and Pilot Readiness

## Goal

Make the MVP secure, reliable, deployable, and ready for use by authenticated users.

## Scope

* Complete authentication and record-ownership authorization checks
* Review sentiment privacy and visibility
* Add database backup procedures
* Define the data-retention approach
* Configure secure password handling
* Configure HTTPS
* Complete automated test coverage for critical workflows
* Test migrations on a clean and existing database
* Test mobile usability
* Test the complete MVP acceptance criteria
* Deploy as a single internal service
* Prepare the application for the pilot
* Document known limitations and operational procedures

## Deliverable

A deployed internal MVP that is secure, backed up, mobile-friendly, and ready for real usage.

## Acceptance Criteria

- All MVP acceptance criteria from the Implementation Plan are satisfied.
- Authentication and record-ownership authorization are enforced on the server.
- Sentiment data is available only to authenticated users, and all authenticated users have the same permissions.
- Passwords are stored using secure password hashing.
- The application is served through HTTPS in the deployed environment.
- SQLite foreign-key enforcement and Write-Ahead Logging are enabled.
- Database backups can be created and restored.
- Database migrations work on both a clean database and an existing database.
- Required data is preserved during migrations and application restarts.
- The application is usable on supported mobile and desktop viewport sizes.
- Critical workflows are covered by automated tests.
- Installation, deployment, backup, restore, and operation procedures are documented.
- A data-retention approach is documented.
- The deployed application does not duplicate core CRM functionality.
- The application is ready for a pilot with actual users.

## Unit Test Gate

- The complete unit test suite must pass.
- All critical authentication and authorization paths must have automated coverage.
- All database constraints and migration-related behavior must have automated coverage where practical.
- Critical meeting, outreach, dashboard, export, and sentiment rules must have automated coverage.
- Run all configured formatting, linting, and type checks.
- Record the commands executed and the results.
- Do not mark the milestone complete while required tests or project checks are failing.

## Manual Test Gate

Complete and document the following manual test checklist.

Record each test with one of these statuses:

- Pass
- Fail
- Blocked

### Manual Test Checklist

#### Full MVP Workflow

- A user can log in and log out.
- A pipeline meeting requires Company plus the three required selections on create.
- A recent meeting requires Company plus the three required selections on edit.
- All five current Meeting outcomes are visible, save correctly, and display correctly.
- Historical meetings without Company or with a legacy outcome still open without an error.

#### Pipeline Meeting taxonomy update

- Pending: Company appears in the required section and is required on create.
- Pending: Company is required on edit and whitespace-only values are rejected.
- Pending: Each of the five current Meeting outcomes saves and displays correctly.
- Pending: Historical missing-Company and legacy-outcome meetings open safely.
- A recent meeting can be deleted or undone according to the implemented behavior.
- A daily outreach record can be created.
- The same daily outreach record can be updated without creating a duplicate.
- Companies contacted equals the sum of the submitted country company counts and is not entered separately.
- The current week is visible immediately after opening the dashboard.
- Activity, progress, engagement, and sentiment are displayed separately.
- Countries and common blockers are visible.
- Authenticated users can export pipeline and outreach data.

#### Authorization and Privacy

- Anonymous users cannot access protected routes by entering their URLs directly.
- All authenticated users have the same application permissions.
- A user cannot edit or delete another user's records by changing the URL or request data.
- Sentiment data is not exposed to unauthenticated users.
- Hidden or unavailable interface actions cannot be executed through direct HTTP requests.
- Passwords are not stored in plaintext.
- Passwords, session tokens, and sensitive notes do not appear in application logs.

#### Database and Migrations

- A new database can be created using the documented migration command.
- All migrations apply successfully to a clean database.
- All migrations apply successfully to a copy of an existing database.
- Existing required data remains available after migration.
- SQLite foreign-key enforcement is active.
- SQLite Write-Ahead Logging is active.
- The application restart does not remove stored records.
- The one-outreach-record-per-user-and-date constraint remains enforced.

#### Backup and Restore

- A database backup can be created using the documented procedure.
- The backup file is created in the expected location.
- A backup can be restored into a test environment.
- Restored users, meetings, outreach records, and country records are available.
- The restored application starts successfully.
- The backup procedure does not require modifying application source code.

#### Deployment and Security

- The deployed service starts using the documented command or service configuration.
- The application is accessible through HTTPS.
- Plain HTTP is redirected to HTTPS or otherwise disabled according to deployment configuration.
- Authentication cookies use secure production settings.
- The deployed service restarts successfully.
- Stored data remains available after a service restart.
- Production secrets are not committed to the repository.

#### Mobile and Usability

- Login is usable on a mobile-sized viewport.
- Meeting entry is usable on a mobile-sized viewport.
- Outreach counters and country controls are usable on a mobile-sized viewport.
- Dashboard content is readable on a mobile-sized viewport.
- Buttons and form controls can be used without horizontal scrolling.
- Meeting entry can reasonably be completed within approximately 10 seconds.
- Daily outreach entry can reasonably be completed within approximately 30 seconds.
- Optional notes are not required to complete either workflow.

#### Documentation and Pilot Readiness

- README installation instructions work in a clean environment.
- Application startup instructions are accurate.
- Migration instructions are accurate.
- Backup and restore instructions are accurate.
- User access and sentiment visibility rules are documented.
- Known limitations are documented.
- The data-retention approach is documented.
- Pilot users can access the deployed application.
- The pilot process includes measuring entry time and collecting feedback.

The milestone is complete only when all required unit tests and project checks pass and all required manual tests are recorded as Pass.

Any Fail or Blocked result must be documented with the reason, owner, and next action.

---

## Suggested Sequence

1. **Milestone 1:** working data-entry application
2. **Milestone 2:** reporting and discussion dashboard
3. **Milestone 3:** production readiness and pilot launch
