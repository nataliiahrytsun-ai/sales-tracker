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

## Run tests

```powershell
python -m pytest
```

## Run project checks

```powershell
python -m compileall -q app tests
```
