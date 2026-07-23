# Milestone 3 Logging and Readiness: Manual Test Checklist

Record each test as **Pass**, **Fail**, or **Blocked**. Use disposable SQLite
databases only; do not make the working user database unavailable for testing.

| Test | Status | Evidence |
| --- | --- | --- |
| The application starts with a disposable database at the current Alembic head | Pass | Local smoke test started the ASGI lifespan with a temporary current-revision database. |
| Startup emits one compact INFO event without a database URL, path, secret, or user data | Pass | Local smoke log contained only the application name, environment, log level, SQLite fact, Secure-cookie state, and allowed-host count. |
| `GET /health` returns HTTP 200 with the documented liveness body | Pass | Local smoke request returned `{"status":"ok"}`. |
| `GET /ready` returns HTTP 200 with the documented readiness body for the current revision | Pass | Local smoke request returned `{"status":"ready"}`. |
| An outdated disposable revision keeps `/health` at 200 and changes `/ready` to 503 | Pass | Local smoke requests returned 200 and 503 respectively. |
| The readiness 503 body omits paths, SQL, tracebacks, revisions, and secrets | Pass | Local smoke response was exactly `{"status":"not_ready"}`. |
| The readiness failure log contains only a safe reason category | Pass | Local smoke log reported `schema revision mismatch` without the configured URL, path, or revision. |
| Hosting readiness configuration targets `/ready`, while liveness targets `/health` | Blocked | Hosting and process-supervisor configuration will be selected later. |
| Log aggregation, retention, and external monitoring ownership are recorded | Blocked | These operational policies require future agreement. |
