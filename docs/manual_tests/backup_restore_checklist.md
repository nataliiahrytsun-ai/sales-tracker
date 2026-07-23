# Milestone 3 SQLite Backup and Restore: Manual Test Checklist

Record each deployment-specific test as **Pass**, **Fail**, or **Blocked**.
Use only a disposable database and existing temporary directories. Never run
restore against the working production database during routine verification.

| Test | Status | Evidence |
| --- | --- | --- |
| A timestamped backup can be created with `python -m app.backup backup` from a disposable SQLite database | Pass | Local smoke test used a temporary database; the command reported a verified backup and the source stayed available. |
| `python -m app.backup verify` reports `integrity_check` success and the expected Alembic revision | Pass | Local smoke verification reported the disposable database revision. |
| The backup contains a known committed record that was present in WAL | Pass | Automated test kept the source connection open with a non-empty WAL; the backup and restored database contained the record. |
| `python -m app.backup restore` creates a separate verified database in an existing directory | Pass | Local smoke restore created a second temporary file with the expected record and revision. |
| Default restore refuses to replace an existing target | Pass | Automated test confirmed refusal and preserved the target bytes. |
| Production backup destination is writable and located on persistent storage | Blocked | Hosting and persistent storage location are not selected yet. |
| A copy is stored off the database disk and can be retrieved | Blocked | Off-host storage is a future deployment decision. |
| Backup frequency, retention, RPO, and operational owner are recorded | Blocked | Policy requires future customer agreement. |
| Application shutdown and maintenance steps for replacing the working production database are rehearsed | Blocked | Must be completed after the production runtime and paths are selected. |
