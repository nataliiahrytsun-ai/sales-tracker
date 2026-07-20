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

| Field                          | Input                                                     |
| ------------------------------ | --------------------------------------------------------- |
| Total outreach activities      | Number counter                                            |
| Companies contacted by country | Country and company count                                 |
| Companies contacted            | Automatically calculated as sum of country company counts |

### Optional fields

| Field            | Input                 |
| ---------------- | --------------------- |
| Replies received | Number counter        |
| Positive replies | Number counter        |
| Meetings booked  | Number counter        |
| User mood        | Difficult, Okay, Good |
| Main blocker     | Predefined tag        |
| Note             | Short optional text   |

### Example country breakdown

| Country     | Companies contacted |
| ----------- | ------------------- |
| Germany     | 15                  |
| Austria     | 8                   |
| Switzerland | 4                   |

The system should allow only one outreach record per user and date.

Users enter the number of companies contacted for each selected country. Companies contacted is calculated automatically as the sum of those country company counts. Users do not enter the aggregate value separately. Because the application does not collect company names or identifiers for outreach, it does not verify uniqueness or perform deduplication. The internal unique_companies field may be retained for backward compatibility; its user-facing meaning is the automatically calculated Companies contacted metric.

## 7. Dashboard

The dashboard should open on the current week by default.

The dashboard is available to all authenticated users.

### Filters

- This week
- Last week
- This month
- Custom date range
- All users
- Individual user

### Dashboard sections

#### Activity

- Pipeline meetings completed
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
- Meetings booked
- Companies contacted by country

#### Sentiment

- Daily mood trend
- Difficult, okay, and good entries
- Common blockers
- Consecutive difficult days
- Changes compared with the previous week

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

**Meeting booking rate** = `meetings booked / companies contacted`

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

Display no more than 3 prompts.

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
