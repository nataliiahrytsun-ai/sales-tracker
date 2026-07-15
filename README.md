# Sales Tracker

Minimal FastAPI foundation for the Sales Tracker application.

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

## Session configuration

Development generates an in-memory session secret when none is configured. Set
a stable secret to keep sessions valid across application restarts:

```powershell
$env:SALES_TRACKER_SESSION_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Production requires both a secret of at least 32 characters and secure cookies:

```powershell
$env:SALES_TRACKER_ENVIRONMENT = "production"
$env:SALES_TRACKER_SESSION_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:SALES_TRACKER_SESSION_COOKIE_SECURE = "true"
```

Session cookies have an explicit finite lifetime of 1,209,600 seconds (14 days)
by default. Override it with a positive number of seconds when a shorter policy
is required:

```powershell
$env:SALES_TRACKER_SESSION_MAX_AGE_SECONDS = "28800"
```

The application refuses to start in production if the secret is missing or the
secure-cookie setting is disabled. Do not place the real secret in source code
or a committed configuration file.

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

Sessions use stateless signed cookies. Logout instructs the browser to delete
its cookie, but the server cannot revoke a copy captured before logout. Such a
copied cookie remains usable until its configured `Max-Age` expires, unless the
user is deleted, made inactive, or has their password changed or reset. Password
changes increment the user's authentication version and revoke older sessions;
ordinary logout does not. Full logout replay revocation would require a
server-side session store or revocation mechanism and is not part of the current
architecture.

## Database and migrations

The application uses `sqlite:///./sales_tracker.db` by default. Override the
connection when needed by setting `SALES_TRACKER_DATABASE_URL` before running the
application or Alembic. The URL must use SQLite:

```powershell
$env:SALES_TRACKER_DATABASE_URL = "sqlite:///./sales_tracker.db"
```

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

## Run tests

```powershell
python -m pytest
```

## Run project checks

```powershell
python -m compileall -q app tests
```
