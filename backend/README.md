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

## Integration

Toss Securities is the default read-only market data provider. Orders run in the browser's local
paper account. See [the consolidated project reference](../AGENTS.md) for endpoint details,
credential setup, caching, rate controls, and limitations. Legacy KIS endpoints remain available;
KIS startup work requires explicit `MARKET_DATA_PROVIDER=kis` configuration.
