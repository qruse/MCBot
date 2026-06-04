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

The frontend home screen includes a dark violet stock dashboard prototype with:

- Domestic and overseas market tabs
- English and Korean language selection
- Stock search over sample symbols
- Watchlist add/remove behavior
- Interactive SVG price chart with candlestick and line modes
- Chart ranges: today live, 1D, 1W, 1M, 1Y, 5Y, and all
- Portfolio signal and research note preview panels
- Dark trading-desk layout with a market ticker, chart summary, and automation status rail

Current market data is sample data only. Live brokerage or market data APIs are not connected yet.

The backend is configured to use MongoDB as the primary NoSQL store for new persisted records.
Local development expects MongoDB at `mongodb://localhost:27017` with database name `mcbot`.

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

Create `backend/.env` for local MongoDB and brokerage API settings:

```env
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:3000
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=mcbot
MONGO_TIMEOUT_MS=2000
KIS_ENV=paper
KIS_APP_KEY=your-kis-app-key
KIS_APP_SECRET=your-kis-app-secret
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

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
