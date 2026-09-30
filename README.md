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

The homepage is a Korean dashboard for server-owned paper sessions and hourly Codex strategy
research. FastAPI owns decimal accounting, risk checks, a durable SQLite ledger and a frozen
reference strategy. Codex reads versioned context and submits expiring proposals through the local
research exchange; there is no LLM API integration or real brokerage order execution.

Start explicitly enables read-only market collection. Observer mode records research proposals;
adaptive paper mode accepts only validated theme/cash plans. Reload preserves state, and backend
restart restores paused. The dashboard shows profit, active policy, expiry, research receipts,
preregistered hypotheses and same-input reference performance. New strategy promotion remains gated.

See [AGENTS.md](AGENTS.md) for the canonical implementation status, commands, research workflow,
limits and hourly operating instructions. Runtime data and SQLite files are ignored.

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
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3001
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
# Only for UI/session-flow changes, with the dev server running on port 3001:
npm run test:e2e
# Only for production, routing, dependency, or build configuration changes:
npm run build
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
