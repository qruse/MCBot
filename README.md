# MCBot

MCBot means **Money Copy Bot**.

This project is a starter for a stock-market automation service that will connect to brokerage
accounts, organize stock-related research data, and eventually support automated trading workflows.

## Current Status

The repository currently contains the first development environment setup:

- `backend/`: Python FastAPI backend
- `frontend/`: Next.js TypeScript frontend
- `test_logs/`: local test logs and screenshots
- `artifacts/`: generated deliverables
- `tmps/`: temporary files

The dashboard uses Toss Securities market data with local paper trading. The existing theme
rotation strategy selects three stocks, applies risk controls, and records session profit every
five seconds after an explicit start. Price charts and synthetic realtime ticks are removed.

Broker requests are independent of profit sampling: batch prices refresh every 30 seconds, FX
is cached for five minutes, and strategy history is loaded only during automation. Global request
pacing, shared caches, and cooldowns protect the API. Credentials are stored only in backend/.env.
See [AGENTS.md](AGENTS.md) for the consolidated provider setup, limits, and current behavior.

## Planned Features

- Brokerage account integration
- Stock watchlists and portfolio summaries
- Market news, filings, indicators, and research material organization
- Trading strategy configuration
- Backtesting and paper-trading mode
- Automated trading execution with risk controls
- Activity logs, alerts, and audit history

## Tech Stack

- Backend: Python 3.12, FastAPI, Pydantic, Uvicorn
- Frontend: Next.js, React, TypeScript
- Tests: pytest, ruff, ESLint, Next.js production build

## Backend

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/brokers/toss/status`

Create `backend/.env` for local MongoDB and brokerage API settings:

```env
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:3001
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=mcbot
MONGO_TIMEOUT_MS=2000
MARKET_DATA_PROVIDER=toss
TOSS_CLIENT_ID=
TOSS_CLIENT_SECRET=
```

## Frontend

```powershell
cd frontend
npm install
npm run dev -- --port 3001
```

Open `http://localhost:3001`.

To change the backend API URL, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Validation

```powershell
cd backend
.\\.venv\\Scripts\\python -m ruff check .
.\\.venv\\Scripts\\python -m pytest

cd ..\\frontend
npm run lint
npm run build
npm audit
```

## Docker Compose

The production-style local stack runs Next.js and FastAPI behind nginx.

```powershell
docker compose build
docker compose up -d
```

Open:

- App: `http://localhost:8080`
- API health: `http://localhost:8080/api/health`
- API docs: `http://localhost:8080/api/docs`

Stop the stack:

```powershell
docker compose down
```

## Safety Notes

Automated trading can create real financial risk. Live trading features should be added only after
broker-specific authentication, permission checks, paper-trading validation, order limits, kill
switches, and complete audit logging are implemented.
