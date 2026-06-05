# MCBot Agent Info

MCBot means Money Copy Bot. The project is planned as a brokerage-connected stock research and
automated trading assistant.

## Main Directories

- `backend/`: Python FastAPI backend
- `frontend/`: Next.js TypeScript frontend
- `test_logs/`: test logs and QA output
- `artifacts/`: finished artifacts
- `tmps/`: temporary files

## Main Code Files

- `backend/app/main.py`: FastAPI app, CORS settings, `/`, and `/health`
- `backend/app/database.py`: MongoDB client helpers, database/collection accessors, and ping
  health check using `MONGO_URI`
- `backend/app/kis.py`: Korea Investment Securities Open API client for the live quote watchlist
  (`NVDA`, `MU`, `SNDK`, `005930`, `000660`) with token, quote, and historical chart caching
- `backend/app/market_data.py`: background 10-second KIS quote refresh scheduler, MongoDB latest
  quote persistence, quote history persistence, intraday chart aggregation, and latest-or-refresh
  API helper
- `backend/tests/test_main.py`: backend endpoint tests
- `backend/Dockerfile`: production backend container image
- `frontend/Dockerfile`: production Next.js standalone container image
- `frontend/src/app/page.tsx`: frontend test page
- `frontend/src/app/StockDashboard.tsx`: interactive stock dashboard prototype
- `frontend/src/app/page.module.css`: test page styles
- `frontend/src/app/layout.tsx`: Next.js metadata and root layout
- `nginx/nginx.conf`: reverse proxy for frontend and `/api/*`
- `compose.yaml`: local multi-container stack

## Data Storage

- MongoDB is the primary NoSQL store for new persisted records.
- Local development uses `MONGO_URI=mongodb://localhost:27017` and `MONGO_DB_NAME=mcbot`.
- Runtime secrets and local database settings live in `backend/.env`; examples live in
  `backend/.env.example`.

## Market Data Integration

- KIS Open API is the active quote provider.
- `GET /quotes/kis/watchlist` returns the focused live quote list for NVIDIA, Micron, Sandisk,
  Samsung Electronics, and SK Hynix.
- `GET /quotes/kis/history/{symbol}?range=LIVE|1D|1W|1M|1Y|5Y|ALL` returns chart-ready OHLC
  candles. `LIVE`/`1D` use Mongo scheduled KIS quote history; longer ranges use KIS chart data.
- FastAPI startup launches a background market data scheduler. It refreshes KIS watchlist quotes
  every `MARKET_DATA_REFRESH_SECONDS` seconds, upserts `market_quote_latest`, and appends
  `market_quote_history` so the service keeps data current even when the frontend is not open.
- Frontend development is served on `http://localhost:3001` for this app.
