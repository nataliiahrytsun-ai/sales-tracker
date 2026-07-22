# Implementation Plan: Sales Vibes

> **Source of truth:** This Markdown document is the maintained
> implementation plan for the project. The DOCX file is retained as a
> historical or exported copy and should not be edited independently.

## 1. Purpose

Build a lightweight internal application that helps the team transparently discuss sales activity, progress, customer sentiment, blockers, and employee sentiment.

The application supports two workflows:

- Short pipeline meetings with potential IT staff augmentation clients
- Daily outbound outreach to new companies across different countries

The application must be extremely simple to use and should require only a few seconds of input.

## 2. Product Boundary

This application is not intended to replace the CRM.

The CRM remains the primary system for:

- Customer and contact records
- Opportunities and pipeline stages
- Proposals
- Revenue forecasting
- Commercial history
- Detailed follow-up activities

The Sales Vibes application is a lightweight check-in and discussion tool.

It should help the team answer:

- What happened this week?
- Are customer conversations progressing?
- How engaged are potential clients?
- What problems or blockers exist?
- How are users feeling?
- Where is support needed?

Only information required for these discussions should be collected.

## 3. Product Principles

### Minimal effort

- Meeting entry should take approximately 10 seconds
- Outreach entry should take less than 30 seconds per day
- Notes should always be optional
- Use buttons, counters, and predefined options instead of text fields
- Automatically fill in user, date, and time

### Transparent reporting

Display activity, customer response, results, and employee sentiment separately.

Avoid introducing a single employee performance score in the MVP.

### No duplicate CRM administration

Do not maintain detailed customer records, opportunities, pipeline stages, or revenue data.

CRM integrations may be added later only when they reduce manual entry.

## 4. Users and Access

All authenticated users have the same permissions and can:

- Record pipeline meeting outcomes
- Update daily outreach activity
- View personal weekly activity
- Edit recent entries
- View weekly team status
- Filter by user and date
- Review sentiment and blockers
- Compare activity and outcomes
- Export data

## 5. Pipeline Meeting Workflow

A user completing pipeline meetings records approximately 5 to 10 short meetings per day.

After each meeting, the user records a small set of structured fields.

### Required fields

| Field               | Options                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| Customer engagement | Low, Medium, High                                                                                    |
| Need identified     | Yes, No, Unclear                                                                                     |
| Outcome             | No fit, Follow-up, Introduction, Proposal requested, Meeting booked, Opportunity identified, Unclear |

### Optional fields

| Field          | Options               |
| -------------- | --------------------- |
| User mood      | Difficult, Okay, Good |
| Blocker        | Predefined tag        |
| Country        | Country selector      |
| Company        | Short text            |
| Next-step date | Date                  |
| Note           | Short optional text   |

### Interaction flow

1. Select customer engagement
2. Select whether a need exists
3. Select the meeting outcome
4. Save

After saving, show:

- Confirmation
- Undo action
- Record another meeting button

The user should not be required to document the full meeting. Detailed customer and opportunity information belongs in the CRM.

## 6. Outreach Workflow

A user completing outreach records one summary per day.

The daily record can be updated throughout the day.

### Required fields

| Field                         | Input          |
| ----------------------------- | -------------- |
| Total outreach activities     | Number counter |
| Replies received              | Number counter |
| Positive replies              | Number counter |
| Meetings booked from outreach | Number counter |

### Optional fields

| Field                          | Input                     |
| ------------------------------ | ------------------------- |
| Companies contacted by country | Country and company count |
| User mood                      | Difficult, Okay, Good     |
| Main blocker                   | Predefined tag            |
| Note                           | Short optional text       |

### Example country breakdown

| Country     | Companies contacted |
| ----------- | ------------------- |
| Germany     | 15                  |
| Austria     | 8                   |
| Switzerland | 4                   |

The system should allow only one outreach record per user and date.

Country rows are optional. When a row is added, both Country and Companies count are required, and the count must be a non-negative whole number; zero is valid. Added rows appear above the Add country control.

Total Companies is displayed read-only and calculated live as the sum of all country company counts. With no country rows, Total Companies is zero. The server recalculates the same value before every save and ignores any submitted aggregate value. Because the total is derived, no country-total mismatch warning is shown. The internal `unique_companies` field is retained for backward compatibility and stores this server-derived Total Companies value.

Because the application does not collect company names or identifiers for outreach, it does not verify uniqueness or perform deduplication.

## 7. Dashboard

The dashboard should open on the current week by default.

The dashboard is available to all authenticated users.

### Filters

- Current week
- Last week
- Current month
- Custom date range
- All users
- Individual user

### Dashboard sections

#### Activity

- Pipeline meetings held
- Outreach activities
- Companies contacted
- Activity per day
- Activity compared with target

#### Customer response and progress

- High-engagement meetings
- Meetings where a need was identified
- Meetings with a concrete next step
- Proposals requested
- Opportunities identified
- Replies received
- Positive replies
- Meetings booked from outreach
- Companies contacted by country

#### Sentiment

- Daily mood trend
- Difficult, okay, and good entries
- Common blockers
- Consecutive difficult days
- Changes compared with the corresponding previous period

### Previous-period comparisons

The Dashboard must compare the main metrics for the selected period with the corresponding previous period. The same date and user filters must govern the numerical comparisons and both series in the `Daily mood trend` chart.

#### Previous-period date ranges

All ranges are inclusive of their start and end dates.

- **Current week:** compare the elapsed part of the current week, from Monday through the current date, with the same weekdays of the previous week. For example, Monday–Wednesday of the current week is compared with Monday–Wednesday of the previous week. Do not compare an incomplete current week with a complete previous week.
- **Last week:** compare the complete previous Monday–Sunday week with the complete Monday–Sunday week immediately before it.
- **Current month:** compare the elapsed part of the current month, from day 1 through the current date, with day 1 through the same day number of the previous month. For example, July 1–20 is compared with June 1–20. If that day number does not exist in the previous month, end the previous range on the last existing day of that month.
- **Custom date range:** compare the selected range with the immediately preceding, non-overlapping range containing the same inclusive number of calendar days. If the selected range is July 10–15, its duration is 6 days and the previous range is July 4–9.

For `Current month`, do not map multiple selected dates to the last day of a shorter previous month. The previous range contains each existing calendar date once and may therefore be shorter than the selected range. For example, March 1–31 is compared with February 1–28 in a non-leap year, so the actual previous range contains 28 days. Selected-period positions beyond the end of that previous range have no previous-period point. The implementation must expose and test the actual duration of the resolved previous range.

The Dashboard must display the actual resolved comparison range, for example:

- `Compared with Jul 6–12, 2026`
- `Compared with Jun 1–20, 2026`

This range label applies to both the numerical comparisons and the previous-period line in `Daily mood trend`. It is especially important for `Current week`, `Current month`, and `Custom date range`.

#### User filtering

Apply exactly the same user filter to both periods:

- `All users` is compared with `All users`;
- an individual user is compared only with that same user's data.

Data from other users must not enter an individual comparison. The same rule applies to both lines in `Daily mood trend`.

#### Metrics with comparisons

Show previous-period comparisons for these `Activity and target progress` metrics:

- Total outreach activities
- Companies contacted
- Replies received
- Positive replies
- Meetings booked from outreach
- Pipeline meetings held

Show previous-period comparisons for these `Pipeline conversion metrics`:

- High-engagement rate
- Need-identification rate
- Concrete-next-step rate
- Proposal rate
- Opportunity-identification rate

Show previous-period comparisons for these `Outreach conversion rates`:

- Reply rate
- Positive reply rate
- Outreach meeting booking rate

Also compare:

- `Average mood` in `Mood summary`;
- `Daily mood trend` as two chart series.

Do not add numerical comparison labels to:

- target values;
- target completion percentages;
- Countries;
- Blockers;
- Comments overview;
- Discussion prompts;
- mood distribution.

#### Numerical comparison format

For quantitative metrics, show the absolute difference, not relative percentage growth:

- `↑ +5 vs previous period`
- `↓ −3 vs previous period`
- `No change`

For conversion rates, show the percentage-point difference, not relative percentage change:

- `↑ +6 pp vs previous period`
- `↓ −4 pp vs previous period`
- `No change`

For example, a change from 20% to 26% is `+6 pp`, not `+30%`.

For `Average mood`, show the numerical difference on the 1–3 mood scale, using the same rounding as the current `Mood summary`:

- `↑ +0.4 vs previous period`
- `↓ −0.3 vs previous period`
- `No change`

Display each comparison as a compact label beneath its primary metric. Do not use large alert blocks, warning styling, or error banners.

#### Comparison colors and non-color cues

- A positive difference uses a green upward arrow and green value text.
- A negative difference uses a red downward arrow and red value text.
- `No change` and unavailable comparisons use neutral gray styling.

Color must not be the only means of communicating the result. Preserve the upward or downward arrow, the `+` or `−` sign, the numerical value, and the descriptive text. A neutral comparison must retain its textual explanation.

#### Missing and non-comparable data

Missing mood must remain missing and must not be converted to `Okay`.

For a quantitative metric, compare with zero only when zero is a trustworthy aggregate for the previous period. Do not invent a zero when the previous value is unknown or undefined.

If a previous-period conversion rate cannot be calculated because its denominator is zero, display:

`No comparable previous rate`

Do not display `NaN`, `Infinity`, a division-by-zero error, or a misleading percentage.

If the previous-period average mood is unavailable, display:

`No previous mood data`

If the current value itself is unavailable, retain the metric's existing empty-data behavior and do not fabricate a numerical difference.

#### Mood scale text

The Dashboard must explain the mood scale with this exact text:

`Mood scale: 1 = Difficult · 2 = Okay · 3 = Good`

#### Daily mood trend

The `Daily mood trend` chart must show the selected and corresponding previous periods simultaneously when previous mood data is available.

The two series are:

- **Selected period:** retain the existing primary-line styling, use a solid line, and label the legend entry `Selected period`.
- **Previous period:** use a green dashed line and label the legend entry `Previous period`.

The green dashed line identifies the previous period; it does not indicate a positive result. The legend must make that meaning clear. The series must remain distinguishable without relying on color alone.

Match chart points by their ordinal position within each range:

- the first selected-period day corresponds to the first previous-period day;
- the second day corresponds to the second day;
- the third day corresponds to the third day;
- and so on.

This maps Monday to Monday for weekly comparisons. For `Custom date range`, use the day's ordinal position in the range. Do not merge the series by equal calendar date because the two periods use different dates. If the previous range is shorter, positions without a previous date remain missing.

The X-axis may continue to display selected-period dates, but the tooltip must state the actual period, date, and value for both points. For example:

- `Selected period — Jul 14: 2.0`
- `Previous period — Jul 7: 2.5`

Do not present a previous-period value under a selected-period date without identifying its actual date.

For missing mood values:

- retain each missing daily value as missing or `null`;
- do not substitute the value 2;
- do not connect a line artificially across a missing day when the chart library supports gaps;
- continue to display the other available previous-period points when only some days are missing.

If the previous period has no mood data at all:

- do not render an empty dashed line;
- retain the selected-period line;
- display the neutral explanation `No previous mood data`.

The chart must meet these accessibility and responsive requirements:

- solid and dashed line styles distinguish the series in addition to color;
- the legend names both series in text;
- tooltips name the period, actual date, and value;
- the legend remains readable and may wrap on mobile;
- the chart does not create horizontal page scrolling on mobile;
- labels are not clipped;
- tooltips fit within the mobile viewport;
- both lines remain visually distinguishable on mobile.

## 8. Core Metrics

### Pipeline metrics

- Total meetings
- High-engagement rate
- Need identification rate
- Concrete next-step rate
- Proposal rate
- Opportunity identification rate

A concrete next step includes:

- Follow-up
- Introduction
- Proposal requested
- Meeting booked
- Opportunity identified

### Outreach metrics

**Reply rate** = `replies / total outreach activities`

**Positive reply rate** = `positive replies / total outreach activities`

**Outreach meeting booking rate** = `meetings booked from outreach / companies contacted`

Meetings booked from outreach remains the sum of Daily Outreach `meetings_booked`. Pipeline meetings held remains the count of filtered Pipeline Meeting records. These clarified user-facing names do not change either data source or calculation.

The application must safely handle empty values and division by zero.

### Sentiment metrics

Mood values may be stored numerically:

- 1 = Difficult
- 2 = Okay
- 3 = Good

Missing sentiment should remain missing and must not automatically be treated as neutral.

The dashboard should show both the average and the distribution.

## 9. Attention Indicators

### Purpose

Discussion prompts are deterministic, non-punitive indicators intended to support team discussion.

They:

- are calculated only from structured dashboard data;
- do not use AI or free-text comment analysis;
- are not employee performance warnings;
- do not create an employee score;
- respect the currently selected date range and user filter.

### Initial MVP rules

#### 1. Consecutive difficult days

Trigger when `Difficult` mood is recorded on at least 2 consecutive calendar dates.

Rules:

- missing mood values do not count as Difficult;
- a calendar date without a Difficult mood record breaks the sequence;
- multiple Difficult records on the same date count as one Difficult date;
- use the longest qualifying sequence within the selected period.

Prompt title:

`Mood pattern`

Prompt message:

`Difficult mood was recorded on {streak_length} consecutive days.`

#### 2. Few concrete next steps

Trigger when:

- total pipeline meetings is at least 4;
- concrete-next-step rate is strictly below 50%.

Exactly 50% must not trigger the prompt.

Use the existing definition of a concrete next step:

- Follow-up
- Introduction
- Proposal requested
- Meeting booked
- Opportunity identified

Prompt title:

`Few concrete next steps`

Prompt message:

`Only {concrete_next_step_count} of {total_meetings} meetings had a concrete next step.`

#### 3. Positive replies without booked meetings

Trigger when:

- positive replies is at least 3;
- meetings booked equals 0.

Prompt title:

`Positive replies without booked meetings`

Prompt message:

`{positive_replies} positive replies were recorded, but no meetings were booked.`

#### 4. Repeated blocker

Trigger when the same non-empty blocker is recorded at least 3 times within the selected data.

Rules:

- ignore null and empty blocker values;
- if multiple blockers qualify, select the blocker with the highest count;
- if counts are equal, use alphabetical order by displayed blocker label as a deterministic tie-breaker.

Prompt title:

`Repeated blocker`

Prompt message:

`{blocker_label} was reported {blocker_count} times.`

### Display rules

Use this fixed priority order:

1. Consecutive difficult days
2. Few concrete next steps
3. Positive replies without booked meetings
4. Repeated blocker

The current MVP supports four prompt types. Display all triggered MVP prompts in the fixed priority order above.

Do not display duplicate prompt types.

Place the section after `Outreach conversion rates` and before `Mood summary`.

When no rule triggers, display:

`No discussion prompts for the selected period.`

The empty state must be neutral and compact.

Do not use:

- Warning
- Poor performance
- Critical
- Failure
- red warning styling
- disciplinary or accusatory language

### Threshold status

These are initial MVP thresholds.

These thresholds may be reviewed after the pilot based on how frequently the prompts appear and whether they improve team discussions.

## 10. Recommended Technology

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy or SQLModel
- Pydantic
- Alembic

### Database

- SQLite
- Foreign key enforcement enabled
- Write-Ahead Logging enabled
- Daily backup

### Frontend

- Jinja2 templates
- HTMX
- Minimal JavaScript
- Chart.js
- Responsive CSS

A server-rendered web application is sufficient. A native mobile application or complex frontend framework is not required.

## 11. Database Model

### Users

```text
id
name
email
password_hash
active
created_at
```

### Pipeline Meetings

```text
id
user_id
occurred_at
company_name
country_code
customer_engagement
need_identified
outcome
user_mood
blocker_tag
next_step_date
note
created_at
updated_at
```

### Daily Outreach

```text
id
user_id
activity_date
total_activities
unique_companies
replies
positive_replies
meetings_booked
user_mood
blocker_tag
note
created_at
updated_at
```

Add a unique constraint on:

`user_id + activity_date`

### Outreach Countries

```text
id
outreach_daily_id
country_code
companies_contacted
```

### Targets

```text
id
user_id
metric_name
target_value
effective_from
effective_until
```

## 12. Main Application Screens

### Home

Show only relevant actions:

- Record meeting
- Update today's outreach
- View this week
- Open Dashboard

### Meeting entry

- Large engagement buttons
- Need identification buttons
- Outcome buttons
- Optional mood and blocker
- One Save button

### Outreach entry

- Large plus and minus counters
- Country breakdown
- Optional mood and blocker
- Automatic update of today's record

### Dashboard

- Weekly summary
- Pipeline results
- Outreach results
- Country breakdown
- Sentiment trend
- Blockers
- Export

## 13. Routes

```text
GET  /login
POST /login
POST /logout

GET  /meetings/new
POST /meetings
GET  /meetings/recent
POST /meetings/{id}
POST /meetings/{id}/delete

GET  /outreach/today
POST /outreach/today
GET  /outreach/{date}
POST /outreach/{date}

GET  /dashboard
GET  /exports/pipeline.csv
GET  /exports/outreach.csv
```

## 14. Implementation Phases

### Phase 1: Product definition

- Confirm fields and outcome options
- Confirm blocker tags
- Define targets
- Confirm sentiment visibility
- Create simple screen mockups

### Phase 2: Application foundation

- Create FastAPI project
- Configure SQLite and migrations
- Implement authentication
- Use one authenticated user type with equal permissions
- Create responsive base layout

### Phase 3: Data entry

- Implement pipeline meeting form
- Implement daily outreach form
- Add editing and deletion
- Add validation and Undo behavior

### Phase 4: Dashboard

- Implement date and user filters
- Add activity metrics
- Add pipeline conversion metrics
- Add outreach metrics
- Add sentiment and blocker views
- Add country breakdown

### Phase 5: Quality and deployment

- Add automated tests
- Add authentication and record-ownership authorization checks
- Add backups
- Test mobile usability
- Configure HTTPS
- Deploy as a single internal service

### Phase 6: Pilot

- Use the application with the actual team
- Measure how long entries take
- Remove unused fields
- Adjust tags and metrics
- Validate that the dashboard improves weekly discussions

## 15. Security and Privacy

Because the application records employee sentiment:

- Clearly explain what is being recorded
- Restrict sentiment data to authenticated users; all authenticated users have the same access
- Use sentiment as a support signal, not as an isolated performance measure
- Do not record or analyze calls in the MVP
- Do not infer emotions from voice or video
- Store only necessary customer information
- Use HTTPS and secure password hashing
- Back up the SQLite database
- Define a data-retention policy

## 16. MVP Acceptance Criteria

The MVP is complete when:

- A meeting can be recorded with three required selections
- A meeting can be saved without notes or customer details
- Outreach can be recorded in one daily summary
- Only one outreach record exists per user and date
- The current week is visible immediately
- Activity, progress, customer engagement, and sentiment are shown separately
- Countries and common blockers are visible
- Users can correct their own recent entries
- Authenticated users can export data
- The application works well on mobile devices
- The application does not duplicate core CRM functionality

## 17. Future Enhancements

Only after the MVP has been validated:

- CRM links or data synchronization
- Calendar-based meeting detection
- Email outreach import
- Automated reminders for missing entries
- Weekly summaries
- Country-level conversion reporting
- Optional AI classification of short notes

Any integration should reduce manual effort rather than add another reporting obligation.
