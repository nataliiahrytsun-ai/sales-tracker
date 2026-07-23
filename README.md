# Sales Tracker

Minimal FastAPI foundation for the Sales Tracker application.

## Product documentation

The maintained product and technical requirements are in
[`docs/implementation-plan.md`](docs/implementation-plan.md). The original
`docs/Implementation_Plan.docx` is retained as a historical/exported copy and
should not be edited independently.

## Requirements

- Python 3.12

## Installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the application

```powershell
python -m uvicorn app.main:app --reload
```

The health-check is available at `http://127.0.0.1:8000/health`.

## Environment and session configuration

Development generates an in-memory session secret when none is configured. Set
a stable secret to keep sessions valid across application restarts:

```powershell
$env:SALES_TRACKER_SESSION_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`SALES_TRACKER_ENVIRONMENT` accepts only `development`, `test`, or
`production`. Its value is trimmed and matched case-insensitively. When the
variable is omitted, the application uses `development` for local
compatibility. An explicitly empty, misspelled, or unknown value stops startup
with a configuration error.

Production requires an explicit session secret of at least 32 characters and
an explicit absolute SQLite database URL whose parent directory already exists
and is writable. The following values are placeholders only:

```powershell
$env:SALES_TRACKER_ENVIRONMENT = "production"
$env:SALES_TRACKER_SESSION_SECRET = "<secret-from-the-deployment-secret-store>"
$env:SALES_TRACKER_SESSION_COOKIE_SECURE = "true"
$env:SALES_TRACKER_DATABASE_URL = "sqlite:///C:/<persistent-directory>/sales_tracker.db"
$env:SALES_TRACKER_ALLOWED_HOSTS = "<production-hostname>"
```

Session cookies have an explicit finite lifetime of 1,209,600 seconds (14 days)
by default. Override it with a positive number of seconds when a shorter policy
is required:

```powershell
$env:SALES_TRACKER_SESSION_MAX_AGE_SECONDS = "28800"
```

`SALES_TRACKER_SESSION_COOKIE_SECURE` defaults to `true` in production and
cannot be set to `false` there. Cookies remain HttpOnly with `SameSite=Lax`.
`SALES_TRACKER_SESSION_MAX_AGE_SECONDS` is optional, but must be a positive
integer when set. Its final production value remains a deployment decision.

Production startup fails if the secret is missing or too short, Secure cookies
are disabled, the database URL is absent or relative, or the database parent
directory is missing or inaccessible. Errors identify the affected environment
variable without printing the session secret. Do not place a real secret in
source code or a committed configuration file.

## Browser security

Every HTML form that changes application state, including login and logout,
contains a cryptographically strong synchronizer token. The token is stored in
the signed session, verified on every `POST`, `PUT`, `PATCH`, and `DELETE`
browser request, and rotated whenever the session is cleared or recreated.
Missing, empty, cross-session, and invalid tokens return HTTP 403. The public
`GET /health` endpoint does not require a token.

Failed login attempts are limited by the direct client address reported by
`request.client.host` together with the trimmed, case-normalized login
identifier. Configure the pilot policy with positive whole numbers:

```powershell
$env:SALES_TRACKER_LOGIN_RATE_LIMIT_MAX_ATTEMPTS = "5"
$env:SALES_TRACKER_LOGIN_RATE_LIMIT_WINDOW_SECONDS = "300"
$env:SALES_TRACKER_LOGIN_RATE_LIMIT_BLOCK_SECONDS = "900"
```

These are the current defaults: five failed attempts in a five-minute window,
followed by a 15-minute block after the allowance is exceeded. Successful login
clears the matching failed-attempt bucket. The limiter stores no passwords and
uses in-memory state for the current one-process, one-worker pilot profile.
State resets on application restart. A future multi-worker or multi-instance
deployment will require a shared limiter store and an agreed final policy.
`X-Forwarded-For` is not trusted; proxy-derived client addresses must wait for
an explicit trusted-proxy configuration.

Trusted Host validation uses a comma-separated
`SALES_TRACKER_ALLOWED_HOSTS` list. Whitespace is trimmed and names are
normalized to lowercase. Exact hostnames and a leading subdomain wildcard such
as `*.example.test` are supported; schemes, ports, paths, and queries are not.
Production requires a non-empty list and rejects the unrestricted `*`.
Development and test default to `localhost`, `127.0.0.1`, and `testserver`.
The real production domain will be selected later.

Responses include:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`, including `frame-ancestors 'none'`
- a restrictive `Permissions-Policy`

The CSP permits only local scripts, styles, fonts, and connections. Inline
scripts are prohibited. Inline styles remain allowed because current Dashboard
and My Week progress visualizations set calculated style values, and `data:`
images remain allowed for the local CSS select-arrow asset. HSTS and HTTPS
redirect are intentionally not enabled until HTTPS termination is confirmed.

## Login

Open `http://127.0.0.1:8000/login` and sign in with the email address of an
existing active user. Authentication uses a signed HttpOnly session cookie.
There is no public registration or automatic seed data.

## User management

Run user-management commands locally after applying migrations:

```powershell
python -m app.cli create-user
python -m app.cli reset-password
```

`create-user` creates a user with a temporary password. On the first login, the
user is redirected to replace it before using the rest of the application.

Use `reset-password` when a user has forgotten their password. Passwords cannot
be recovered; the command can only set a new temporary password. It invalidates
the user's existing authenticated sessions, and the temporary password must be
changed after the next login.

### Known session limitation

Sessions use stateless signed cookies. Logout clears authentication state and
rotates the CSRF token, but the server cannot revoke a cookie copy captured
before logout. Such a copied cookie remains usable until its configured
`Max-Age` expires, unless the user is deleted, made inactive, or has their
password changed or reset. Password changes increment the user's authentication
version and revoke older sessions; ordinary logout does not. Full logout replay
revocation would require a server-side session store or revocation mechanism
and is not part of the current architecture.

## Database and migrations

Development and test use `sqlite:///./sales_tracker.db` by default. Override the
connection when needed by setting `SALES_TRACKER_DATABASE_URL` before running
the application or Alembic. The URL must use SQLite:

```powershell
$env:SALES_TRACKER_DATABASE_URL = "sqlite:///./sales_tracker.db"
```

In production, `SALES_TRACKER_DATABASE_URL` is mandatory and its SQLite file
path must be absolute so it never depends on the process working directory.
Both Windows drive paths and POSIX root paths are recognized. The application
does not create a missing production parent directory; provision persistent
storage before startup. The concrete production path, hosting provider, domain,
HTTPS termination, and proxy settings will be selected later.

Create or update the database to the latest migration:

```powershell
python -m alembic upgrade head
```

The migration chain currently runs through password-state revision
`20260715_0005`. Running `upgrade head` applies all migrations to a new database
and only pending migrations to an existing database.

Create a migration after changing SQLModel metadata:

```powershell
python -m alembic revision --autogenerate -m "describe schema change"
```

Inspect the applied and available revisions:

```powershell
python -m alembic current
python -m alembic heads
```

## SQLite backup and local restore

The operational commands use Python's SQLite backup API, so a backup includes
committed data that is still in the source database's WAL. They do not copy
`.db-wal` or `.db-shm` files. The backup destination and restore target parent
directories must already exist and be writable; the commands never create
those directories silently.

Create a timestamped UTC backup from the centrally configured
`SALES_TRACKER_DATABASE_URL`:

```powershell
New-Item -ItemType Directory -Path "<existing-backup-directory>"
python -m app.backup backup --destination-dir "<existing-backup-directory>"
```

For a deliberate alternate SQLite source, pass its existing database URL:

```powershell
python -m app.backup backup --destination-dir "<existing-backup-directory>" --database-url "sqlite:///C:/<existing-directory>/<source>.db"
```

Every backup is first written to a temporary file, checked with
`PRAGMA integrity_check`, and required to contain a readable
`alembic_version`. It is published under a name such as
`sales_tracker_backup_20260723T140506123456Z.db` only after verification and
never overwrites an existing backup. Verify an artifact again without changing
it:

```powershell
python -m app.backup verify "<existing-backup-directory>\sales_tracker_backup_<UTC-timestamp>.db"
```

Restore into a separate file in an existing directory:

```powershell
New-Item -ItemType Directory -Path "<existing-restore-directory>"
python -m app.backup restore "<backup-file>.db" "<existing-restore-directory>\restored.db"
```

Restore verifies the source and the temporary restored database before an
atomic publish. It refuses to overwrite an existing target unless `--replace`
is explicitly supplied, does not modify the backup, and does not run Alembic.
Stop the application before using `--replace` on a working production
database, and resolve any WAL/SHM sidecars first.

A backup stored on the same disk does not protect against loss of that disk.
Backup frequency, retention, off-host storage, recovery point objective (RPO),
and production scheduling remain to be agreed before deployment.

## Run tests

```powershell
python -m pytest
```

## Run project checks

```powershell
python -m compileall -q app tests
```
