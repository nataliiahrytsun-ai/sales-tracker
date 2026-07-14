# Sales Vibes

Minimal FastAPI foundation for the Sales Vibes application.

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

The migration chain currently contains the initial Alembic setup followed by
product-table revision `20260714_0002`. Running `upgrade head` applies both
migrations to a new database and only pending migrations to an existing
database.

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
