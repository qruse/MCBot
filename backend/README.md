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
- `GET /quotes/kis/watchlist`: latest KIS watchlist quotes persisted by the background MongoDB
  refresh scheduler

## Market Data Scheduler

The backend starts a background KIS quote refresh loop during FastAPI startup. It refreshes the
watchlist every `MARKET_DATA_REFRESH_SECONDS` seconds, stores the latest quote per symbol in
`market_quote_latest`, and appends each refresh point to `market_quote_history`.
