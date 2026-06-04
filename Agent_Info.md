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
- `backend/tests/test_main.py`: backend endpoint tests
- `frontend/src/app/page.tsx`: frontend test page
- `frontend/src/app/page.module.css`: test page styles
- `frontend/src/app/layout.tsx`: Next.js metadata and root layout
