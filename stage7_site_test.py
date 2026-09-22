#!/usr/bin/env python3
"""
Stage 7 -- Real full-system test runner (parameterized).

One-off test-artifact producer, not a reusable production test harness
(validate_orchestrator.py / validate_integration.py remain the canonical
Stage 5/6 suites and are not touched or superseded by this file).

Usage:
    .venv\\Scripts\\python.exe stage7_site_test.py <site_url> <output_filename>

Two passes, both bounded by the approved Stage 5 limits (never increased):

  1. PRIMARY: run the real agent-facing entrypoint (orchestrate.py) as an
     actual subprocess, using the package's own .venv interpreter -- this is
     the authoritative pass/fail signal, matching the Stage 6 contract.

  2. DIAGNOSTIC (secondary, read-only): the public report schema
     intentionally does not expose crawl-trace detail (URLs discovered,
     per-page HTTP status, what got rendered). To show that detail without
     modifying frozen Stage 5 code, this calls the exact same shared-crawl
     function orchestrate.py itself uses internally
     (orchestrate._run_shared_crawl), with the same bounds, as a second,
     separate, still-bounded, still-robots-respecting pass.

Everything is written to the given output filename. Each result file is a
test artifact only -- nothing in it is read back into production logic.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.join(ROOT, "brand-ai-readiness-audit")
# .venv lives at the dev root, one level above the marketplace root, so the
# marketplace root itself stays free of dev-only artifacts for submission.
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ORCHESTRATE_PATH = os.path.join(PKG_ROOT, "skills", "audit-orchestrator", "scripts", "orchestrate.py")
REPORT_BUILDER_PATH = os.path.join(PKG_ROOT, "skills", "audit-orchestrator", "scripts", "report_builder.py")
SKILLS_DIR = os.path.join(PKG_ROOT, "skills")
SKILL_DIR_NAMES = ["audit-orchestrator", "crawl-render-audit", "freshness-corroboration", "engagement-audit"]


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def list_tmp_artifacts() -> list[str]:
    found = []
    for skill_dir in SKILL_DIR_NAMES:
        scripts_dir = os.path.join(SKILLS_DIR, skill_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            continue
        for fname in os.listdir(scripts_dir):
            if fname.startswith("_") and "tmp" in fname:
                found.append(os.path.join(scripts_dir, fname))
    return found


def main(site_url: str, out_path: str) -> None:
    result: dict = {
        "test_website": site_url,
        "test_started_at": datetime.now(timezone.utc).isoformat(),
    }

    before_tmp = list_tmp_artifacts()

    print(f"[1/2] Running orchestrate.py as a real subprocess against {site_url} ...")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [VENV_PYTHON, ORCHESTRATE_PATH, site_url],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=340,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        proc = None
        print(f"  TIMEOUT after {exc.timeout}s")
    subprocess_duration = round(time.time() - t0, 1)
    print(f"  done in {subprocess_duration}s, exit_code={proc.returncode if proc else 'TIMEOUT'}")

    after_tmp = list_tmp_artifacts()

    stdout_json = None
    stdout_json_error = None
    if proc is not None:
        try:
            stdout_json = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            stdout_json_error = str(exc)

    report_builder = load_module(REPORT_BUILDER_PATH, f"s7_report_builder_{abs(hash(out_path))}")
    schema_errors = report_builder.validate_report(stdout_json) if stdout_json is not None else ["no report parsed"]

    result["subprocess"] = {
        "interpreter": VENV_PYTHON,
        "script": ORCHESTRATE_PATH,
        "timed_out": timed_out,
        "exit_code": (proc.returncode if proc else None),
        "duration_s": subprocess_duration,
        "stdout_parsed_as_json": stdout_json is not None,
        "stdout_json_error": stdout_json_error,
        "stderr": (proc.stderr if proc else None),
        "stderr_is_empty": (proc.stderr.strip() == "" if proc else None),
        "schema_validation_errors": schema_errors,
        "new_temp_artifacts_after_run": sorted(set(after_tmp) - set(before_tmp)),
    }
    result["final_report"] = stdout_json

    print("[2/2] Running a separate diagnostic-only crawl pass (same bounds) to capture crawl-trace detail ...")
    orch = load_module(ORCHESTRATE_PATH, f"s7_orchestrate_diag_{abs(hash(out_path))}")
    cr_mods = orch._get_crawl_render()

    diag_error = None
    robots_data = crawl_result = render_comparisons = None
    t1 = time.time()
    try:
        robots_data, crawl_result, render_comparisons = orch._run_shared_crawl(
            site_url, cr_mods,
            max_pages=orch.DEFAULT_MAX_PAGES,
            max_depth=orch.DEFAULT_MAX_DEPTH,
            render_max=orch.DEFAULT_RENDER_MAX,
        )
    except Exception as exc:
        diag_error = str(exc)
    diag_duration = round(time.time() - t1, 1)
    print(f"  done in {diag_duration}s (error={diag_error})")

    pages = (crawl_result or {}).get("pages", [])
    crawl_errors = (crawl_result or {}).get("errors", [])
    rendered_urls = {c.get("url") for c in (render_comparisons or [])}

    page_trace = []
    for p in pages:
        url = p.get("final_url") or p.get("url")
        page_trace.append({
            "url": p.get("url"),
            "final_url": p.get("final_url"),
            "status": p.get("status"),
            "depth": p.get("depth"),
            "redirects": p.get("redirects"),
            "response_time_ms": p.get("response_time_ms"),
            "content_type": p.get("content_type"),
            "body_length": len(p.get("body") or ""),
            "rendered": url in rendered_urls,
        })

    result["diagnostic_crawl"] = {
        "note": (
            "Separate, read-only diagnostic pass using the same approved bounds and the "
            "exact same shared-crawl function orchestrate.py itself calls internally "
            "(orchestrate._run_shared_crawl). Not used to alter the authoritative "
            "subprocess report above -- provided only because the public report schema "
            "intentionally omits crawl-trace detail (see finding-schema.md)."
        ),
        "duration_s": diag_duration,
        "error": diag_error,
        "robots_txt": ({
            "exists": (robots_data or {}).get("exists"),
            "error": (robots_data or {}).get("error"),
            "sitemap_urls_count": len((robots_data or {}).get("sitemap_urls", [])),
        } if robots_data is not None else None),
        "urls_discovered": (crawl_result or {}).get("urls_discovered"),
        "urls_crawled": (crawl_result or {}).get("urls_crawled"),
        "pages_rendered": len(render_comparisons or []),
        "crawl_errors": crawl_errors,
        "page_trace": page_trace,
        "render_comparisons": render_comparisons,
    }

    result["test_finished_at"] = datetime.now(timezone.utc).isoformat()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python stage7_site_test.py <site_url> <output_filename>")
        sys.exit(1)
    main(sys.argv[1], os.path.join(ROOT, sys.argv[2]))
