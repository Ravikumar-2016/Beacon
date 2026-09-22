# Beacon — AI Readiness Audit

Beacon audits any public website for **AI discoverability** (can AI
assistants find, access, and confidently use its content?) and **on-site
engagement** (can a visitor who lands there orient, navigate, and take a
useful next action?). Give it a URL and it hands back a structured,
evidence-backed report: findings ranked by severity, each with the evidence
behind it and a concrete suggested fix.

It's a web frontend on top of the [`brand-ai-readiness-audit`](brand-ai-readiness-audit/)
engine — a deterministic, read-only audit tool (see that folder's own
[README](brand-ai-readiness-audit/README.md) for how the checks themselves
work).

```
BrandAiReadinessAudit/
├── brand-ai-readiness-audit/   # the audit engine (skills marketplace) — read-only, unmodified
├── backend/                    # FastAPI wrapper exposing the engine over HTTP
└── frontend/                   # React + Tailwind UI
```

## Prerequisites

- **Python 3.12+**
- **Node.js 20+** and npm

## Setup

Clone the repo:

```bash
git clone https://github.com/Ravikumar-2016/Beacon.git
cd Beacon
```

### Backend

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
python -m playwright install chromium
```

### Frontend

```bash
cd frontend
npm install
cd ..
```

## Run it

Two terminals, both from the repo root.

**Terminal 1 — backend:**

```bash
python -m uvicorn main:app --app-dir backend --port 8000
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**, enter a URL, and run an audit. The Vite dev
server proxies `/api/*` to the backend on port 8000 (see
`frontend/vite.config.ts`) — no extra configuration needed.

A full audit crawls up to 15 pages and can take a few minutes; the UI shows
live progress while it runs.

## API

The backend exposes two endpoints (see `backend/main.py`):

- `POST /api/audits` — body `{"url": "https://example.com"}` → `{ id, status }`.
  Starts an audit as a background job.
- `GET /api/audits/{id}` — returns the job's `status`
  (`queued` / `running` / `done` / `error`), and `report` once done.

Audits run as background jobs rather than a single long request, since a
full crawl can take a few minutes.

## About the audit engine

The engine underneath (`brand-ai-readiness-audit/`) is:

- **Read-only / recommendation-only** — never modifies the target site, no
  form submissions, no logins.
- **Respects `robots.txt`** — won't crawl disallowed paths.
- **Bounded** — max 15 pages, depth 3, 3 rendered pages, no rate abuse.

See its own [README](brand-ai-readiness-audit/README.md) for the full
architecture (four cooperating skills: orchestrator, crawl/render,
freshness/corroboration, engagement) and the report schema.

## Troubleshooting

- **`playwright install chromium` fails or hangs** — make sure the venv is
  activated first; the browser installs into that environment.
- **Frontend can't reach the backend** — confirm the backend is running on
  port 8000 before starting `npm run dev`, and that nothing else is bound
  to either port 5173 or 8000.
- **Audit takes a long time on a large site** — expected; it's bounded but
  a full crawl + render pass can take a few minutes.
