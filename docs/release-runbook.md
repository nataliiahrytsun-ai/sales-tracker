# Sales Tracker Release and Rollback Runbook

This runbook defines a provider-agnostic release process for the current
single-process, single-worker SQLite deployment profile. The hosting provider,
domain, HTTPS termination, process supervision, and production filesystem
paths remain deployment decisions.

Use placeholders in this document only after resolving them to reviewed
deployment-specific values. Production secrets must come from the deployment
secret store and must never be committed to the repository.

## Release prerequisites

Before changing the running version:

1. Identify the exact commit selected for release and confirm that its GitHub
   Actions `quality-gate` completed successfully.
2. Record the commit hash of the version currently serving users. Keep it as
   the rollback application version.
3. Confirm that `SALES_TRACKER_DATABASE_URL` points to persistent SQLite
   storage. Do not release against ephemeral or working-directory storage.
4. Confirm that the existing backup destination directory is writable and
   create a pre-release backup:

   ```powershell
   python -m app.backup backup --destination-dir "<existing-backup-directory>"
   ```

5. Verify the resulting backup independently:

   ```powershell
   python -m app.backup verify "<pre-release-backup-file>"
   ```

6. Record the exact path of the verified pre-release backup in the release
   record.
7. Confirm operationally that no restore is in progress. Investigate any
   `.restore.tmp` file instead of deleting or replacing it blindly.
8. If the selected release contains a migration, agree on a short maintenance
   window in which the application can remain stopped until migration and
   verification finish.

Do not start the release without a known previous commit and a verified
pre-release backup.

## Release procedure

1. Stop the current application process before changing the production SQLite
   database. Ensure no application worker or instance retains a connection.
2. Obtain the exact selected, CI-verified commit using the deployment
   environment's normal source retrieval mechanism. Verify its commit hash.
3. Using Python 3.12, install the project dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -e "."
   ```

4. Load the reviewed production environment variables from the deployment
   environment. Do not print them or store them in the repository.
5. With the application still stopped, migrate the configured database:

   ```powershell
   python -m alembic upgrade head
   ```

6. Start one application process with one worker using the existing Uvicorn
   entry point:

   ```powershell
   python -m uvicorn app.main:app
   ```

   Binding and process supervision are deployment-specific and are not defined
   here. Multiple workers or application instances sharing SQLite are not
   supported by the current pilot architecture.

7. Verify the already running application:

   ```powershell
   python -m app.release_check --base-url "<application-http-or-https-origin>"
   ```

   The command checks `GET /health` first and `GET /ready` second. It does not
   send authentication or cookies and does not follow redirects.
8. Confirm that `/health` returned HTTP 200 with `{"status":"ok"}`.
9. Confirm that `/ready` returned HTTP 200 with `{"status":"ready"}`.
10. Open `/login` manually, sign in with a designated test account, and open
    one authenticated application page.
11. Only after all automated and manual checks pass, end the maintenance window
    and allow normal user traffic.

`/health` proves only that the process responds. `/ready` proves that SQLite is
reachable and its Alembic revision matches the application's migration head.
HTTP 200 from `/health` together with HTTP 503 from `/ready` is a failed
release. Migrations must finish before user traffic is admitted. Future
deployment automation must depend on a successful CI quality gate.

## Rollback decision

Stop the failing new application version before rollback. Determine from the
release record and migration output whether `alembic upgrade head` changed the
schema.

Never perform an automatic `alembic downgrade`. Never start an older
application version against a potentially incompatible newer schema. Choose
one of the following scenarios explicitly.

### Rollback without a schema change

Use this path only when no migration was applied, or when there is documented
evidence that the previous application version is compatible with the current
schema:

1. Keep the new application stopped.
2. Reconfirm the recorded previous, CI-verified commit.
3. Return the application files and dependencies to that exact commit.
4. Keep the database unchanged only when schema compatibility is established.
5. Start one application process with the previous version.
6. Run `app.release_check`.
7. Manually verify login and one authenticated page.
8. Reopen user traffic only after `/health`, `/ready`, and manual checks pass.

### Rollback after a schema change

The safe baseline is:

```text
stop application
→ restore verified pre-release backup
→ return to previous commit
→ start application
→ health/readiness/manual checks
```

Detailed procedure:

1. Keep every application worker or instance stopped.
2. Confirm the exact verified pre-release backup and previous commit recorded
   before release.
3. Restore the backup into a separate file in an existing writable directory:

   ```powershell
   python -m app.backup restore "<pre-release-backup-file>" "<existing-restore-directory>/rollback-candidate.db"
   ```

4. Verify the restored candidate:

   ```powershell
   python -m app.backup verify "<existing-restore-directory>/rollback-candidate.db"
   ```

5. Review and explicitly approve the data-loss boundary. Restoring the
   pre-release backup removes all data written after that backup was created.
   This must be a deliberate operational decision, not an automatic action.
6. With the application still stopped and SQLite WAL/SHM sidecars resolved,
   atomically replace the configured production database through the existing
   restore command:

   ```powershell
   python -m app.backup restore "<existing-restore-directory>/rollback-candidate.db" "<production-database-file>" --replace
   ```

7. Return the application files and dependencies to the recorded previous
   commit.
8. Start one application process with the previous version.
9. Run `app.release_check`.
10. Manually verify login and one authenticated page.
11. Reopen traffic only after `/health`, `/ready`, and manual checks pass.

If backup identity, schema compatibility, data-loss approval, or the previous
commit is uncertain, keep the application stopped and escalate the decision.
Do not improvise a destructive rollback.
