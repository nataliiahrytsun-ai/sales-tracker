# Milestone 1 Database Configuration: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Alembic configuration loads and exposes one head revision | Pass | `alembic heads` reported `20260714_0001 (head)` and `alembic check` found no new operations. |
| Migrations apply to a clean SQLite database | Pass | `alembic upgrade head` completed successfully against a new temporary database configured through `SALES_TRACKER_DATABASE_URL`. |
| The clean database records the initial Alembic revision | Pass | `alembic current` and the `alembic_version` table reported `20260714_0001`; no product tables exist. |
| New SQLite connections report `foreign_keys = 1` | Pass | `PRAGMA foreign_keys` returned `1` through the application engine. |
| The migrated SQLite database reports `journal_mode = wal` | Pass | `PRAGMA journal_mode` returned `wal`. |
