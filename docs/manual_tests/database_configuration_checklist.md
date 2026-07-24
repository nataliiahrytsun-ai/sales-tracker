# Milestone 1 Database Configuration: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**.

| Test | Status | Evidence |
| --- | --- | --- |
| Alembic configuration loads and exposes one head revision | Pass | 2026-07-24: `alembic heads` reported `20260721_0008 (head)`. Historical evidence for `20260714_0003` was valid before later migrations and is superseded by this current-head check. |
| Migrations apply to a clean SQLite database | Pass | 2026-07-24, local temporary SQLite: `alembic upgrade head` applied revisions `20260714_0001` through `20260721_0008` against an absolute temporary URL outside the repository. |
| The clean database records the current Alembic revision | Pass | 2026-07-24, local temporary SQLite: readiness returned HTTP 200 `{"status":"ready"}` after migration to `20260721_0008`; the earlier `20260714_0003` record is historical and superseded. |
| New SQLite connections report `foreign_keys = 1` | Pass | `PRAGMA foreign_keys` returned `1` through the application engine. |
| The migrated SQLite database reports `journal_mode = wal` | Pass | `PRAGMA journal_mode` returned `wal`. |
