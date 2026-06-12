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
- `backend/app/universe.py`: curated first-pass theme universe API data with theme-level top
  market-cap top 10 metadata for dashboard strategy experiments
- `backend/tests/test_main.py`: backend endpoint tests
- `backend/Dockerfile`: production backend container image
- `frontend/Dockerfile`: production Next.js standalone container image
- `frontend/src/app/page.tsx`: frontend test page
- `frontend/src/app/StockDashboard.tsx`: interactive stock dashboard prototype
- `frontend/src/app/page.module.css`: test page styles
- `frontend/playwright.config.ts`: Chrome-channel Playwright e2e settings for local dashboard QA
- `frontend/tests/dashboard.spec.ts`: rendered dashboard interaction test for market tabs, chart mode,
  paper-trading controls, theme graphs, and screenshots
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
  every `MARKET_DATA_REFRESH_SECONDS` seconds, defaulting to 1 second for first-pass trading
  simulation work, upserts `market_quote_latest`, and appends
  `market_quote_history` so the service keeps data current even when the frontend is not open.
- Frontend development is served on `http://localhost:3001` for this app.
- `GET /universe/themes` returns curated theme/sector groups and top market-cap top 10 metadata.
- The frontend dashboard now includes a denser brokerage-style candlestick chart, 1-second simulated
  ticks, a configurable paper-trading account defaulting to 100,000,000 KRW with reset, and a
  theme-rotation automation panel.
- The dashboard stock list is grouped by theme, supports domestic/overseas paper-trading views, and
  falls back to seeded historical candles when very short realtime buffers would make the chart flat.
- The main chart uses a classic brokerage-style candlestick view with 5/20/60/120 moving averages,
  high/low labels, right-side price ticks, volume bars, and realtime quote scaling over stable history.
- Chart x-axis labels use deterministic date/time formatting: intraday ranges show month/day and
  hour/minute, mid ranges include short year/month/day and hour/minute, and long ranges show dates.
- Chart ranges separate live market hours from 1-day history: `LIVE` renders the regular trading
  session, while `1D` renders a 24-hour window with dark-theme chart styling.
- The paper-trading simulation uses Korea Investment Securities fee assumptions: BanKIS domestic
  online KRX commission at 0.0140527%, and US online overseas trading at 0.25% buy / 0.25206% sell
  including the US SEC sell fee.
- Paper-trading orders allocate the configured account balance across the target top 3 but only buy
  whole shares; any amount that cannot buy at least one more share remains as cash.
- The dashboard has a theme/universe refresh button that refetches `/universe/themes` so market-cap
  top lists can be refreshed without reloading the app.
- The automation guardrails reduce churn through stricter theme MA rollover confirmation instead of
  time locks: rollover requires fast/slow MA spread weakness, fast MA decline, weak stock score, and
  at least 7 of the theme top 10 showing the same deterioration.
