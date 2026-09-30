# Repository Guidelines

## Project Overview

MCBot (Money Copy Bot) is a starter stock-market automation service. The repository is split into:

- `backend/`: Python 3.12 FastAPI service.
- `frontend/`: Next.js, React, and TypeScript web app.
- `nginx/`: Local reverse-proxy configuration for Docker Compose.
- `artifacts/`, `test_logs/`, and `tmps/`: Generated outputs, local logs, screenshots, and temporary files.

Toss Securities is the default market data provider. Trading execution remains local paper trading. Treat anything related to live trading, brokerage integration, credentials, order execution, or financial decisions as high risk.

## Safety and Product Constraints

- Do not add live trading, order placement, or brokerage-account functionality without explicit user direction.
- Keep secrets out of the repository. Use `.env.example` for documented environment variables and local `.env*` files for real values.
- Preserve risk controls, auditability, and paper-trading validation when adding future trading-related features.

## Backend Workflow

Work from `backend/` for Python changes.

```bash
cd backend
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest
```

Backend conventions:

- Target Python 3.12.
- Use FastAPI and Pydantic idiomatically.
- Keep Ruff clean; configured line length is 100 characters.
- Add or update tests under `backend/tests/` for behavior changes.

## Frontend Workflow

Work from `frontend/` for UI changes.

```bash
cd frontend
npm install
npm run lint
npm run build
```

Frontend conventions:

- Follow the scoped `frontend/AGENTS.md` instructions before changing frontend files.
- Use TypeScript and React components consistently with the existing app structure.
- Keep sample-data UI clearly distinguishable from live market data.
- If a perceptible UI change is made, capture a screenshot when practical.

## Docker Compose Workflow

Use the production-style local stack from the repository root:

```bash
docker compose build
docker compose up -d
docker compose down
```

App URLs:

- App: `http://localhost:8080`
- API health: `http://localhost:8080/api/health`
- API docs: `http://localhost:8080/api/docs`

## General Development Notes

- Prefer small, focused changes with matching validation.
- Do not commit generated dependencies such as `node_modules/`, Python virtual environments, or cache directories.
- Keep documentation in sync when commands, environment variables, or user-facing behavior changes.

## Current Direction and Integration Reference

- All work and deliverables are in English; chat responses to the owner are in Korean.
- Keep the workspace clean and use the minimum lightweight validation necessary.
- Consolidate project reference information in this file. `frontend/AGENTS.md` retains scoped
  framework instructions. Do not maintain a separate Agent_Info.md.
- The dashboard preserves theme rotation, balanced top-three whole-share paper allocations,
  2% position stops, moving-average exits, and the 5% holding-loss sidecar.
- Price charts, candlesticks, volume plots, theme sparklines, and synthetic ticks are removed.
- Toss batch prices are polled every 30 seconds without overlapping requests. USD/KRW is cached
  for five minutes. Strategy history loads only after start, for the selected market, sequentially
  with a 15-minute refresh; minute candles cache for 15 minutes and daily candles for one hour.
  No artificial history is used for decisions. Entries require at least 26 minute bars and
  80 daily bars, current prices, and fresh strategy data for the selected market.
- Paper orders stay in browser memory. Reloading clears the account and session. Stopping pauses
  orders and profit sampling; resuming keeps the same baseline. Reset stops and clears both.
- The session profit graph is hidden before start. Start records zero against current net paper
  equity; every five seconds records equity minus the starting baseline. Failed price requests or
  snapshots older than 90 seconds suspend sampling. Five-second graph values use the latest cached
  market snapshot, not a fresh API call. Estimates include commissions but exclude taxes/other
  charges; this is not
  realized brokerage profit. Paper commissions assume domestic KRX 0.015% and US 0.1% per side.
- New provider module: `backend/app/toss.py`. Endpoints: `/brokers/toss/status`, `/connection`,
  `/prices?symbols=...`, and `/strategy/{symbol}` under that prefix. Connection checks return only
  account identifiers/types, never account numbers. No brokerage order endpoints are exposed.
- Credentials: set `TOSS_CLIENT_ID` and `TOSS_CLIENT_SECRET` in ignored `backend/.env`.
  Obtain these at Toss Securities WTS > Settings > Open API. Register the execution server's
  public outbound IP in the allowed-IP list. The backend obtains and refreshes OAuth tokens;
  never paste keys/tokens into chats or commit them. Restart the backend after changing `.env`.
- Docker Compose optionally loads `backend/.env`. `MARKET_DATA_PROVIDER=toss` is the default.
  Legacy KIS modules/endpoints remain for compatibility; their startup scheduler and history
  download run only when `MARKET_DATA_PROVIDER=kis` is explicitly selected.
- Official references (verified 2026-09-30):
  https://developers.tossinvest.com/llms.txt
  https://openapi.tossinvest.com/openapi-docs/latest/openapi.json
  https://developers.tossinvest.com/docs
  https://home.tossinvest.com/ko/open-api
- Canonical Toss base URL: `https://openapi.tossinvest.com`; OAuth uses form-encoded
  `POST /oauth2/token` with client credentials. Business responses are wrapped in `result`.
  Batch prices: `GET /api/v1/prices?symbols=...` (up to 200), decimal-string `lastPrice`.
  FX: `GET /api/v1/exchange-rate`, decimal-string `rate`.
  Candles: `GET /api/v1/candles` with `symbol`, `interval=1m|1d`, `count<=200`;
  `result.candles` uses `openPrice/highPrice/lowPrice/closePrice`, newest first.
  Account lookup: `GET /api/v1/accounts`. Requests are paced and token issuance serialized;
  all outgoing calls including OAuth have at least 3.1 seconds spacing (at most 20 per rolling
  minute per process). Shared caches deduplicate refreshes and browser tabs. 429 waits at least
  five minutes or a longer Retry-After; 401/403 suspend further outbound calls until backend
  restart after fixing credentials/IP. Other failures wait at least 60 seconds. Response bodies
  are redacted. Keep one backend worker/instance for this credential set; limits are process-local.
- Current paper session follows regular weekday market hours in Seoul/New York. Exchange holidays
  and exceptional schedules are not yet incorporated. Do not enable live execution with this logic.
- Minimal checks: backend Ruff and pytest; frontend ESLint/build; one Playwright session lifecycle
  check with mocked Toss data, including start/5-second sample/stop/resume/reset and no price chart.

- Validation on 2026-09-30: backend Ruff and 23 pytest tests passed; frontend ESLint and production
  build passed; mocked Playwright session lifecycle passed. One real OAuth token request and one
  account-list request confirmed connection to one account. No brokerage orders were submitted.
