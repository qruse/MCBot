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
