# MCBot Backend

FastAPI backend for Money Copy Bot.

## Run

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Test

```powershell
python -m ruff check .
python -m pytest
```

## Endpoints

- `GET /`: backend status message
- `GET /health`: health-check response
- `GET /docs`: FastAPI Swagger documentation
