# MCBot Frontend

Next.js TypeScript frontend for Money Copy Bot.

## Run

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`.

## Environment

Create `.env.local` when the backend URL is different from the default:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Test

```powershell
npm run lint
npm run build
npm audit
```
