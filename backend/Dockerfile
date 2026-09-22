# Build context is the repo root (see render.yaml: dockerContext: .)
# so this can COPY the audit engine, which lives next to backend/.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY brand-ai-readiness-audit/requirements.txt ./brand-ai-readiness-audit/requirements.txt
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Installs Chromium plus whatever system libraries this Playwright version needs.
RUN playwright install --with-deps chromium

COPY brand-ai-readiness-audit ./brand-ai-readiness-audit
COPY backend ./backend

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
