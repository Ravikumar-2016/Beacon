"""
Audit Orchestrator — Main orchestration logic.

Coordinates the full AI-readiness audit:
1. Validates target URL.
2. Performs ONE shared robots/crawl/render pass (crawl-render-audit's own
   crawl.py/robots_check.py/render.py — no specialist crawls independently).
3. Invokes the three specialist skills against that same shared evidence.
4. Collects findings, isolating any single specialist's failure.
5. Deduplicates findings.
6. Resolves severity.
7. Produces the final structured report.

Skill directories use hyphens and cannot be imported as normal Python
packages, and each specialist audit_runner.py uses relative imports scoped to
its own scripts/ folder. This module locates and loads them dynamically,
relative to its own file location — the same proven approach used by
validate_audit.py / validate_freshness_audit.py / validate_engagement_audit.py.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
CR_SCRIPTS = os.path.join(SKILLS_DIR, "crawl-render-audit", "scripts")
FC_SCRIPTS = os.path.join(SKILLS_DIR, "freshness-corroboration", "scripts")
EA_SCRIPTS = os.path.join(SKILLS_DIR, "engagement-audit", "scripts")

# Approved Stage 5 execution bounds — keep the whole audit comfortably within
# the project's 5-minute runtime target. Do not silently increase these.
DEFAULT_MAX_PAGES = 15
DEFAULT_MAX_DEPTH = 3
DEFAULT_RENDER_MAX = 3
DEFAULT_MAX_SAMEAS_LINKS = 5
DEFAULT_MAX_LINK_CHECKS = 20
DEFAULT_MAX_VIEWPORT_PAGES = 2

_module_cache: dict[str, Any] = {}


def validate_url(url: str) -> str:
    """Validate and normalize the target URL.

    Returns the normalized URL or raises ValueError.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https scheme, got: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError(f"URL must have a valid domain: {url!r}")
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc


# ---------------------------------------------------------------------------
# Dynamic module loading (no normal package imports across hyphenated dirs)
# ---------------------------------------------------------------------------


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_specialist(scripts_dir: str, leaf_names: list[str], namespace: str) -> dict[str, Any]:
    """Dynamically load one specialist skill's scripts (leaf modules +
    audit_runner.py), rewriting audit_runner.py's relative imports to
    absolute ones so it resolves against the already-loaded leaf modules.
    """
    # Leaf modules are registered under their BARE names (not namespaced) —
    # audit_runner.py's imports get rewritten below to plain `from <name>
    # import ...`, which resolves via sys.modules[<name>]. This is safe
    # because the three specialist skills' leaf module names do not collide
    # with each other (verified: crawl-render / freshness / engagement each
    # use distinct leaf filenames).
    mods: dict[str, Any] = {}
    for name in leaf_names:
        mods[name] = _load_module(os.path.join(scripts_dir, f"{name}.py"), name)

    ar_path = os.path.join(scripts_dir, "audit_runner.py")
    with open(ar_path, encoding="utf-8") as f:
        src = f.read()
    for name in leaf_names:
        src = src.replace(f"from .{name} import", f"from {name} import")

    tmp_path = os.path.join(scripts_dir, f"_{namespace}_audit_runner_tmp.py")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        mods["audit_runner"] = _load_module(tmp_path, f"{namespace}_audit_runner")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return mods


def _get_crawl_render():
    if "cr" not in _module_cache:
        _module_cache["cr"] = _load_specialist(
            CR_SCRIPTS,
            ["html_analysis", "link_analysis", "metadata_analysis", "structured_data",
             "robots_check", "crawl", "render"],
            "cr",
        )
    return _module_cache["cr"]


def _get_freshness():
    if "fc" not in _module_cache:
        _module_cache["fc"] = _load_specialist(
            FC_SCRIPTS,
            ["identity_analysis", "freshness_analysis", "fact_consistency", "corroboration"],
            "fc",
        )
    return _module_cache["fc"]


def _get_engagement():
    if "ea" not in _module_cache:
        _module_cache["ea"] = _load_specialist(
            EA_SCRIPTS,
            ["page_orientation", "navigation_analysis", "cta_analysis", "link_health",
             "viewport_check", "engagement_analysis"],
            "ea",
        )
    return _module_cache["ea"]


def _get_sibling(name: str):
    """Load one of audit-orchestrator's own sibling scripts (finding_deduplicator,
    severity, report_builder). Loaded the same dynamic way — not via a relative
    import — so this module works whether run directly or loaded by a harness.
    """
    key = f"orch_{name}"
    if key not in _module_cache:
        _module_cache[key] = _load_module(os.path.join(THIS_DIR, f"{name}.py"), key)
    return _module_cache[key]


# ---------------------------------------------------------------------------
# Shared crawl/render pass (performed exactly once, reused by all specialists)
# ---------------------------------------------------------------------------


def _run_shared_crawl(
    site_url: str,
    cr_mods: dict[str, Any],
    max_pages: int,
    max_depth: int,
    render_max: int,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    """Perform the ONE shared robots/crawl/render pass reused by all three
    specialists. Mirrors the pipeline already validated in Stage 2's
    validate_audit.py, relocated here as the production implementation.
    """
    robots_data: dict[str, Any] | None = None
    try:
        robots_data = cr_mods["robots_check"].fetch_robots_txt(site_url, timeout=10)
    except Exception as exc:
        log.warning("robots.txt fetch failed for %s: %s", site_url, exc)

    is_allowed = None
    if robots_data and robots_data.get("parser"):
        parser = robots_data["parser"]
        is_allowed = lambda url: parser.can_fetch("BrandAIReadinessAudit", url)

    try:
        crawl_result = cr_mods["crawl"].bounded_crawl(
            site_url, is_allowed=is_allowed, max_pages=max_pages, max_depth=max_depth, timeout=12,
        )
    except Exception as exc:
        log.warning("crawl failed for %s: %s", site_url, exc)
        crawl_result = {
            "pages": [], "sitemap_urls": [], "urls_discovered": 0, "urls_crawled": 0,
            "errors": [{"url": site_url, "error": str(exc)}],
        }

    pages = crawl_result.get("pages", [])
    render_comparisons: list[dict[str, Any]] = []
    if pages and cr_mods["render"].is_playwright_available():
        urls_to_render = [p.get("final_url") or p.get("url") for p in pages[:render_max]]
        try:
            rendered_results = cr_mods["render"].render_multiple_pages(urls_to_render, timeout_ms=25000)
            for page_data, rdata in zip(pages[:render_max], rendered_results):
                if rdata.get("error"):
                    continue
                raw_html = page_data.get("body", "") or ""
                try:
                    raw_text = cr_mods["html_analysis"].extract_visible_text(raw_html)
                    raw_headings = cr_mods["html_analysis"].extract_headings(
                        BeautifulSoup(raw_html, "html.parser"))
                except Exception:
                    raw_text, raw_headings = "", {}
                comp = cr_mods["render"].compare_raw_vs_rendered(
                    raw_text, rdata.get("rendered_text") or "", raw_headings, rdata.get("rendered_headings", {}))
                comp["url"] = page_data.get("final_url") or page_data.get("url", "")
                comp["missing_headings"] = comp.get("headings_only_in_rendered", [])
                render_comparisons.append(comp)
        except Exception as exc:
            log.warning("render comparison failed for %s: %s", site_url, exc)

    return robots_data, crawl_result, render_comparisons


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_audit(
    site_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    render_max: int = DEFAULT_RENDER_MAX,
    max_sameas_links: int = DEFAULT_MAX_SAMEAS_LINKS,
    max_link_checks: int = DEFAULT_MAX_LINK_CHECKS,
    max_viewport_pages: int = DEFAULT_MAX_VIEWPORT_PAGES,
    external_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the full audit pipeline.

    Args:
        site_url: The target website URL.
        max_pages, max_depth, render_max, max_sameas_links, max_link_checks,
            max_viewport_pages: Bounded execution limits (see module
            constants for approved defaults — do not increase silently).
        external_sources: Optional pre-judged external source verdicts for
            freshness-corroboration's F5 Tier B corroboration (see that
            skill's corroboration.py docstring). This deterministic
            orchestrator never performs its own web search; it only passes
            this through for a smarter caller (e.g. an agent that already
            gathered bounded search results) to supply. Defaults to None,
            meaning F5 runs Tier A (sameAs reachability) only.

    Returns:
        The final audit report as a dictionary, conforming to the schema
        produced by report_builder.build_report(). If one or more
        specialist skills failed, a non-schema "_diagnostics" key is added
        alongside the public report fields — this is operational
        information about the audit run itself, never a claim about the
        website, and is not part of the required public schema.

    Raises:
        ValueError: if site_url is not a valid http(s) URL. Malformed URLs
            are not silently handled — this must propagate.
    """
    url = validate_url(site_url)
    domain = extract_domain(url)

    cr_mods = _get_crawl_render()
    fc_mods = _get_freshness()
    ea_mods = _get_engagement()

    robots_data, crawl_result, render_comparisons = _run_shared_crawl(
        url, cr_mods, max_pages=max_pages, max_depth=max_depth, render_max=render_max,
    )

    all_findings: list[dict[str, Any]] = []
    specialist_errors: list[str] = []

    try:
        all_findings += cr_mods["audit_runner"].run_crawl_audit(crawl_result, robots_data, render_comparisons)
    except Exception as exc:
        log.error("crawl-render-audit specialist failed: %s", exc)
        specialist_errors.append(f"crawl-render-audit: {exc}")

    try:
        all_findings += fc_mods["audit_runner"].run_freshness_audit(
            crawl_result, external_sources=external_sources, max_sameas_links=max_sameas_links,
        )
    except Exception as exc:
        log.error("freshness-corroboration specialist failed: %s", exc)
        specialist_errors.append(f"freshness-corroboration: {exc}")

    try:
        all_findings += ea_mods["audit_runner"].run_engagement_audit(
            crawl_result, max_link_checks=max_link_checks, max_viewport_pages=max_viewport_pages,
            render_comparisons=render_comparisons,
        )
    except Exception as exc:
        log.error("engagement-audit specialist failed: %s", exc)
        specialist_errors.append(f"engagement-audit: {exc}")

    # Proactive suggestions: evidence-gated enhancement opportunities, not
    # defects. Kept fully separate from all_findings so they can never
    # affect deduplication, severity scoring, or the findings/summary
    # counts. Each specialist's check is isolated the same way its main
    # audit call is above -- a failure here must never fail the whole run.
    proactive_suggestions: list[dict[str, Any]] = []

    try:
        proactive_suggestions += cr_mods["audit_runner"].identify_proactive_opportunities(
            crawl_result, robots_data,
        )
    except Exception as exc:
        log.error("crawl-render-audit proactive check failed: %s", exc)
        specialist_errors.append(f"crawl-render-audit (proactive): {exc}")

    try:
        proactive_suggestions += fc_mods["audit_runner"].identify_proactive_opportunities(crawl_result)
    except Exception as exc:
        log.error("freshness-corroboration proactive check failed: %s", exc)
        specialist_errors.append(f"freshness-corroboration (proactive): {exc}")

    try:
        proactive_suggestions += ea_mods["audit_runner"].identify_proactive_opportunities(
            crawl_result, render_comparisons=render_comparisons,
        )
    except Exception as exc:
        log.error("engagement-audit proactive check failed: %s", exc)
        specialist_errors.append(f"engagement-audit (proactive): {exc}")

    finding_deduplicator = _get_sibling("finding_deduplicator")
    severity = _get_sibling("severity")
    report_builder = _get_sibling("report_builder")

    deduplicated = finding_deduplicator.deduplicate(all_findings)
    scored = severity.resolve_severities(deduplicated)
    report = report_builder.build_report(domain, scored)

    if proactive_suggestions:
        report["proactive_suggestions"] = [
            {**s, "id": f"P-{i:03d}"} for i, s in enumerate(proactive_suggestions[:5], start=1)
        ]

    if specialist_errors:
        # Diagnostic information about this run, not a website finding —
        # kept outside the schema-required fields.
        report["_diagnostics"] = {"specialist_errors": specialist_errors}

    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orchestrate.py <url>")
        sys.exit(1)
    result = run_audit(sys.argv[1])
    print(json.dumps(result, indent=2))
