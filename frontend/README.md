# Beacon frontend

React + TypeScript + Tailwind v4 UI for the Beacon AI-readiness audit tool.
See the [repo root README](../README.md) for full setup instructions (this
frontend + the FastAPI backend).

## Local development

```bash
npm install
npm run dev
```

Requires the backend running on port 8000 — the dev server proxies `/api`
to it (see `vite.config.ts`).

## Build

```bash
npm run build   # type-checks then builds to dist/
```
