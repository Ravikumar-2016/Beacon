# Beacon — AI Readiness Audit

A web frontend for the `brand-ai-readiness-audit` engine. Enter a URL, Beacon
crawls it and reports on AI discoverability and on-site engagement with a
prioritized, evidence-backed fix list.

```
BrandAiReadinessAudit/
├── brand-ai-readiness-audit/   # the audit engine (skills marketplace) — unchanged
├── backend/                    # FastAPI wrapper exposing the engine over HTTP
└── frontend/                   # React + Tailwind UI
```

## Run it

**Backend** (from the repo root, using the existing `.venv`):

```bash
.venv/Scripts/python.exe -m pip install -r brand-ai-readiness-audit/requirements.txt fastapi "uvicorn[standard]"
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --port 8000
```

**Frontend** (in a second terminal):

```bash
cd frontend
npm install
npm run dev
```

Open the printed `http://localhost:5173` URL. The Vite dev server proxies
`/api/*` to the backend on port 8000 (see `frontend/vite.config.ts`).

## API

- `POST /api/audits {"url": "https://example.com"}` → `{ id, status }`
- `GET /api/audits/{id}` → job status, and `report` once `status` is `"done"`

Audits run as background jobs (they can take a few minutes), so the frontend
polls for status rather than holding one long request open.

## Deploying

Split the deploy: **frontend → Vercel**, **backend → Render**. Vercel's
serverless functions can't run this backend — audits take up to ~5 minutes
(past any serverless timeout) and need a real Chromium browser plus
in-memory job state, none of which fit a stateless function. Render runs it
as a normal always-on Docker container instead.

### 1. Push to GitHub

Render deploys from a connected Git repo.

```bash
git add -A
git commit -m "Prepare for deployment"
git push -u origin main
```

### 2. Backend on Render

1. [render.com](https://render.com) → **New +** → **Blueprint** → connect
   this repo. Render reads [`render.yaml`](render.yaml) and builds
   [`backend/Dockerfile`](backend/Dockerfile) (which installs Chromium via
   `playwright install --with-deps chromium`).
2. Once deployed, copy the service URL, e.g. `https://beacon-backend.onrender.com`.
3. The free plan spins down after 15 minutes idle — the first request after
   that takes ~30–60s to cold-start. Upgrade the plan if that's not
   acceptable, or if audits are hitting the free tier's 512MB RAM limit.

### 3. Frontend on Vercel

1. [vercel.com](https://vercel.com) → **Add New** → **Project** → import
   this repo, with **Root Directory** set to `frontend`. Vercel
   auto-detects Vite (build command `npm run build`, output `dist`).
2. Add an environment variable: `VITE_API_BASE_URL` = your Render backend
   URL from step 2 (see `frontend/.env.example`).
3. Deploy. Your site is live at the Vercel-assigned URL (or a custom domain
   you attach in the project's Domains settings).

Or from the CLI, run `npx vercel` inside `frontend/` and follow the prompts
(it asks for env vars during setup, or add them after via `vercel env add`).
