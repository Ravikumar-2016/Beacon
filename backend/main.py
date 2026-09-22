"""
Beacon API — thin FastAPI wrapper around the Brand AI-Readiness Audit engine.

Runs each audit as a background job (audits can take up to ~5 minutes) so the
frontend can poll for status instead of holding one long HTTP request open.
Does not modify the underlying audit engine in brand-ai-readiness-audit/.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import time
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("beacon-api")

THIS_DIR = Path(__file__).resolve().parent
ORCH_PATH = THIS_DIR.parent / "brand-ai-readiness-audit" / "skills" / "audit-orchestrator" / "scripts" / "orchestrate.py"

if not ORCH_PATH.exists():
    raise RuntimeError(f"Audit orchestrator not found at {ORCH_PATH}")


def _load_orchestrator():
    spec = importlib.util.spec_from_file_location("orchestrate", ORCH_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orchestrate"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


orchestrate = _load_orchestrator()

app = FastAPI(title="Beacon API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JobStatus = Literal["queued", "running", "done", "error"]


class Job(BaseModel):
    id: str
    url: str
    status: JobStatus = "queued"
    created_at: float
    finished_at: float | None = None
    report: dict[str, Any] | None = None
    error: str | None = None


JOBS: dict[str, Job] = {}


class AuditRequest(BaseModel):
    url: str = Field(..., min_length=3, description="Target website URL, e.g. https://example.com")


class AuditCreatedResponse(BaseModel):
    id: str
    status: JobStatus


async def _run_job(job_id: str) -> None:
    job = JOBS[job_id]
    job.status = "running"
    try:
        report = await asyncio.to_thread(orchestrate.run_audit, job.url)
        job.report = report
        job.status = "done"
    except ValueError as exc:
        job.status = "error"
        job.error = str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("audit job %s failed", job_id)
        job.status = "error"
        job.error = f"Audit failed: {exc}"
    finally:
        job.finished_at = time.time()


@app.post("/api/audits", response_model=AuditCreatedResponse)
async def create_audit(payload: AuditRequest) -> AuditCreatedResponse:
    try:
        url = orchestrate.validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = Job(id=job_id, url=url, created_at=time.time())
    asyncio.create_task(_run_job(job_id))
    return AuditCreatedResponse(id=job_id, status="queued")


@app.get("/api/audits/{job_id}", response_model=Job)
async def get_audit(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit job not found")
    return job


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
