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
There is no public registration or automatic seed data; account provisioning is
outside this implementation step.

### Known session limitation

Sessions use stateless signed cookies. Logout instructs the browser to delete
its cookie, but the server cannot revoke a copy captured before logout. Such a
copied cookie remains usable until its configured `Max-Age` expires, unless the
user is deleted or made inactive. Server-side replay revocation would require a
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

The migration chain currently contains the initial Alembic setup, product-table
revision `20260714_0002`, and model-cleanup revision `20260714_0003`. Running
`upgrade head` applies all migrations to a new database and only pending
migrations to an existing database.

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
