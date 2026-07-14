# Milestone 1 Product Models: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Apply all migrations to a clean SQLite database | Pass | `alembic upgrade head` applied revisions `20260714_0001` and `20260714_0002`; `alembic check` found no pending operations. |
| Verify all five product tables exist | Pass | `users`, `pipeline_meetings`, `daily_outreach`, `outreach_countries`, and `targets` were present with `alembic_version`. |
| Verify product foreign keys exist and enforcement is enabled | Pass | `PRAGMA foreign_keys` returned `1`; all four child tables reported a foreign key and an invalid target insert raised `IntegrityError`. |
| Verify duplicate Daily Outreach user/date records are rejected | Pass | A second insert for the same `user_id` and `activity_date` raised `IntegrityError`. |
| Verify omitted meeting and outreach mood values remain `NULL` | Pass | SQL `user_mood IS NULL` returned `1` for both inserted records. |
| Verify duplicate user email addresses are rejected | Pass | A second insert using the same email raised `IntegrityError` after revision `20260714_0003`. |
| Verify new users default to `active = true` | Pass | A direct SQL insert omitting `active` stored `active = 1`. |
| Verify meeting and outreach `updated_at` values change after updates | Pass | Both ORM updates produced timestamps greater than their original values. |
| Verify the mood field name remains consistent | Pass | Implementation Plan, models, migration `0002`, tests, and checklist all use `user_mood`. |
