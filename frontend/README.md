# Beacon frontend

React + TypeScript + Tailwind v4 UI for the Beacon AI-readiness audit tool.
See the [repo root README](../README.md) for how to run and deploy the full
project (this frontend + the FastAPI backend).

## Local development

```bash
npm install
npm run dev
```

Requires the backend running on port 8000 — the dev server proxies `/api`
to it (see `vite.config.ts`). No `.env` needed locally.

## Build

```bash
npm run build   # type-checks then builds to dist/
```

## Environment

`VITE_API_BASE_URL` — the backend's origin in production (e.g. on Vercel).
Leave unset locally. See `.env.example`.
