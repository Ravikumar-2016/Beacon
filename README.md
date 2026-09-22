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
