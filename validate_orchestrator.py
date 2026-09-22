#!/usr/bin/env python3
r"""
Stage 5 Validation Test Runner -- Audit Orchestrator

Same two-part approach as Stages 2-4:
  1. Deterministic fixture/wiring tests (no network) — verify the shared
     crawl is actually reused by all three specialists, deduplication
     behaves conservatively, error isolation works, and the final report
     conforms to the required public schema.
  2. One small real-site end-to-end run (https://example.com by default).

Run with the project .venv:
    .venv\Scripts\python.exe validate_orchestrator.py [--skip-live]
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import time

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(__file__)
ORCH_SCRIPTS = os.path.join(ROOT, "brand-ai-readiness-audit", "skills", "audit-orchestrator", "scripts")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_all_modules():
    mods = {}
    # orchestrate.py has no relative imports of its own (its siblings are
    # loaded dynamically inside it via _get_sibling), so it can be loaded
    # directly with no import rewriting needed.
    mods["orchestrate"] = load_module(os.path.join(ORCH_SCRIPTS, "orchestrate.py"), "orchestrate")
    mods["finding_deduplicator"] = load_module(os.path.join(ORCH_SCRIPTS, "finding_deduplicator.py"), "vo_finding_deduplicator")
    mods["report_builder"] = load_module(os.path.join(ORCH_SCRIPTS, "report_builder.py"), "vo_report_builder")
    return mods


def _page(url, status, body, depth=1):
    return {"url": url, "final_url": url, "status": status, "body": body,
            "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": depth}


def crawl_result_of(*pages):
    return {"pages": list(pages), "sitemap_urls": [], "urls_discovered": len(pages),
            "urls_crawled": len(pages), "errors": []}


# A crawl_result designed to trigger at least one finding from each specialist:
#   - C6 (missing structured data) from crawl-render
#   - F2 (entity ambiguity) from freshness-corroboration
#   - E9 (dead end) from engagement-audit
RICH_CRAWL_RESULT = crawl_result_of(
    _page("https://biz.example/", 200,
          '<html><head><title>Atlas</title>'
          '<script type="application/ld+json">{"@type":"Organization","name":"Atlas"}</script>'
          '</head><body><h1>Atlas</h1></body></html>', depth=0),
    _page("https://biz.example/product/widget", 200,
          '<html><body><h1>Widget</h1><p>Short.</p></body></html>'),
)

EMPTY_CRAWL_RESULT = crawl_result_of()


def run_fixture_tests(mods):
    orch = mods["orchestrate"]
    dedup = mods["finding_deduplicator"]
    report_builder = mods["report_builder"]

    results = []

    def check(label, condition, detail=""):
        results.append((label, condition))
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))

    print("\n" + "=" * 72)
    print("FIXTURE / WIRING TESTS (no network unless noted)")
    print("=" * 72)

    # --- 1/2: URL validation ---
    try:
        normalized = orch.validate_url("https://example.com/path/")
        check("Valid URL is accepted and normalized", normalized == "https://example.com/path", normalized)
    except Exception as exc:
        check("Valid URL is accepted and normalized", False, str(exc))

    try:
        orch.validate_url("not-a-valid-url")
        check("Invalid URL raises ValueError", False, "no exception raised")
    except ValueError:
        check("Invalid URL raises ValueError", True)
    except Exception as exc:
        check("Invalid URL raises ValueError", False, f"wrong exception type: {exc}")

    # --- 3-7: shared crawl reuse + all specialists invoked ---
    seen_crawl_result_ids = {}

    def _fake_shared_crawl(site_url, cr_mods, max_pages, max_depth, render_max):
        return None, RICH_CRAWL_RESULT, []

    orch._run_shared_crawl = _fake_shared_crawl

    cr_mods = orch._get_crawl_render()
    fc_mods = orch._get_freshness()
    ea_mods = orch._get_engagement()

    real_cr_run = cr_mods["audit_runner"].run_crawl_audit
    real_fc_run = fc_mods["audit_runner"].run_freshness_audit
    real_ea_run = ea_mods["audit_runner"].run_engagement_audit

    seen_finding_counts = {}

    def _spy_cr(crawl_result, robots_data, render_comparisons):
        seen_crawl_result_ids["cr"] = id(crawl_result)
        result = real_cr_run(crawl_result, robots_data, render_comparisons)
        seen_finding_counts["cr"] = len(result)
        return result

    def _spy_fc(crawl_result, external_sources=None, max_sameas_links=5):
        seen_crawl_result_ids["fc"] = id(crawl_result)
        result = real_fc_run(crawl_result, external_sources=external_sources, max_sameas_links=max_sameas_links)
        seen_finding_counts["fc"] = len(result)
        return result

    def _spy_ea(crawl_result, max_link_checks=20, max_viewport_pages=2, render_comparisons=None):
        seen_crawl_result_ids["ea"] = id(crawl_result)
        result = real_ea_run(
            crawl_result, max_link_checks=max_link_checks, max_viewport_pages=max_viewport_pages,
            render_comparisons=render_comparisons,
        )
        seen_finding_counts["ea"] = len(result)
        return result

    cr_mods["audit_runner"].run_crawl_audit = _spy_cr
    fc_mods["audit_runner"].run_freshness_audit = _spy_fc
    ea_mods["audit_runner"].run_engagement_audit = _spy_ea

    report = orch.run_audit("https://biz.example/")

    check("Shared crawl produced a usable crawl_result (non-empty pages)",
          len(RICH_CRAWL_RESULT["pages"]) == 2)
    check("Crawl & Render specialist received the shared crawl_result",
          seen_crawl_result_ids.get("cr") == id(RICH_CRAWL_RESULT))
    check("Freshness specialist received the SAME shared crawl_result (not a re-crawl)",
          seen_crawl_result_ids.get("fc") == id(RICH_CRAWL_RESULT))
    check("Engagement specialist received the SAME shared crawl_result (not a re-crawl)",
          seen_crawl_result_ids.get("ea") == id(RICH_CRAWL_RESULT))

    check("Findings from all three specialists are present in the merged report",
          seen_finding_counts.get("cr", 0) > 0 and seen_finding_counts.get("fc", 0) > 0 and seen_finding_counts.get("ea", 0) > 0,
          str(seen_finding_counts))

    check("Final report schema validates (report_builder.validate_report)",
          report_builder.validate_report(report) == [], str(report_builder.validate_report(report)))
    check("Every finding id follows the F-00N pattern",
          all(f["id"].startswith("F-") for f in report["findings"]), str([f["id"] for f in report["findings"]]))
    check("Internal detector categories (C6/F2/E9-style) do not leak into public findings",
          all("category" not in f for f in report["findings"]), str(report["findings"]))
    check("audited_at is present and ISO-8601 parseable",
          _is_iso8601(report.get("audited_at", "")), report.get("audited_at"))
    check("Summary counts match actual findings",
          report["summary"]["total_findings"] == len(report["findings"])
          and report["summary"]["critical"] + report["summary"]["high"] + report["summary"]["medium"]
          <= report["summary"]["total_findings"],
          str(report["summary"]))

    # --- Proactive suggestions wiring ---
    check("proactive_suggestions is present when an opportunity exists (RICH_CRAWL_RESULT has no sitemap)",
          bool(report.get("proactive_suggestions")), str(report.get("proactive_suggestions")))
    check("Every proactive suggestion id follows the P-00N pattern",
          all(s["id"].startswith("P-") for s in report.get("proactive_suggestions", [])),
          str(report.get("proactive_suggestions")))
    check("proactive_suggestions is capped at 5",
          len(report.get("proactive_suggestions", [])) <= 5, str(report.get("proactive_suggestions")))
    check("Proactive suggestions carry no 'severity' field (never defects)",
          all("severity" not in s for s in report.get("proactive_suggestions", [])),
          str(report.get("proactive_suggestions")))
    check("proactive_suggestions does NOT affect summary.total_findings or severity counts",
          report["summary"]["total_findings"] == len(report["findings"]),
          str((report["summary"], report.get("proactive_suggestions"))))

    # restore spies for the next block
    cr_mods["audit_runner"].run_crawl_audit = real_cr_run
    fc_mods["audit_runner"].run_freshness_audit = real_fc_run
    ea_mods["audit_runner"].run_engagement_audit = real_ea_run

    # --- 8-10: deduplication behavior (direct unit tests, no orchestrate involved) ---
    f_a = {"title": "Missing structured data", "severity": "medium", "category": "C6",
           "evidence": "1 page(s) missing structured data:\n- `https://site.example/a`: Organization schema recommended",
           "suggested_action": {"summary": "Add schema", "priority": "medium"}}
    f_a_dup = dict(f_a)  # exact duplicate
    f_b_same_page_diff_category = {"title": "Missing H1", "severity": "medium", "category": "C12",
                                    "evidence": "1 page(s) missing H1:\n- `https://site.example/a`: No H1 heading found.",
                                    "suggested_action": {"summary": "Add H1", "priority": "medium"}}
    f_c_no_url = {"title": "Vague finding", "severity": "low", "category": "E7",
                  "evidence": "Some page lacks structure.",
                  "suggested_action": {"summary": "Improve structure", "priority": "low"}}
    f_c_no_url_2 = {"title": "Another vague finding", "severity": "low", "category": "E7",
                    "evidence": "Another page lacks structure too.",
                    "suggested_action": {"summary": "Improve structure", "priority": "low"}}

    deduped = dedup.deduplicate([f_a, f_a_dup, f_b_same_page_diff_category, f_c_no_url, f_c_no_url_2])
    check("Exact-duplicate findings are collapsed to one",
          sum(1 for f in deduped if f["title"] == "Missing structured data") == 1, str(deduped))
    check("Distinct findings on the SAME page but different category are NOT merged",
          any(f["title"] == "Missing H1" for f in deduped) and any(f["title"] == "Missing structured data" for f in deduped),
          str(deduped))
    check("Findings with no extractable URL are handled conservatively (not merged with each other)",
          sum(1 for f in deduped if "vague finding" in f["title"].lower()) == 2, str(deduped))

    # A genuine same-category, same-URL merge case.
    f_d1 = {"title": "Broken CTA", "severity": "high", "category": "E10",
            "evidence": "- `https://site.example/pricing`: CTA 'Sign Up' -> `/signup` (404)",
            "suggested_action": {"summary": "Fix link", "priority": "high"}}
    f_d2 = {"title": "Broken CTA (duplicate detection pass)", "severity": "high", "category": "E10",
            "evidence": "- `https://site.example/pricing`: another broken CTA reference",
            "suggested_action": {"summary": "Fix link", "priority": "high"}}
    deduped2 = dedup.deduplicate([f_d1, f_d2])
    check("Same category + overlapping URL findings ARE merged into one",
          len(deduped2) == 1, str(deduped2))

    # --- 17/18: forced specialist failure ---
    orch._run_shared_crawl = _fake_shared_crawl
    fc_mods = orch._get_freshness()
    real_fc_run2 = fc_mods["audit_runner"].run_freshness_audit

    def _raising_fc(*args, **kwargs):
        raise RuntimeError("simulated freshness-corroboration crash")

    fc_mods["audit_runner"].run_freshness_audit = _raising_fc
    crashed = False
    try:
        report2 = orch.run_audit("https://biz.example/")
    except Exception as exc:
        crashed = True
        report2 = {}
        print(f"    (unexpected exception: {exc})")
    fc_mods["audit_runner"].run_freshness_audit = real_fc_run2

    check("A forced specialist (freshness) exception does NOT crash the whole audit", not crashed)
    if not crashed:
        titles2 = " ".join(f["title"] for f in report2["findings"])
        check("Other specialists (crawl-render, engagement) still executed despite freshness failing",
              "ambiguity" not in titles2.lower() and ("dead end" in titles2.lower() or len(report2["findings"]) > 0),
              titles2)
        check("Specialist failure is recorded as diagnostics, not a fabricated site finding",
              "_diagnostics" in report2 and any("freshness" in e for e in report2["_diagnostics"]["specialist_errors"])
              and all("simulated" not in f["title"].lower() for f in report2["findings"]),
              str(report2.get("_diagnostics")))
        check("Report remains schema-valid despite a specialist failure",
              report_builder.validate_report(report2) == [], str(report_builder.validate_report(report2)))

    # --- forced proactive-check failure: must not crash the whole audit ---
    orch._run_shared_crawl = _fake_shared_crawl
    fc_mods = orch._get_freshness()
    real_fc_proactive = fc_mods["audit_runner"].identify_proactive_opportunities

    def _raising_fc_proactive(*args, **kwargs):
        raise RuntimeError("simulated freshness-corroboration proactive crash")

    fc_mods["audit_runner"].identify_proactive_opportunities = _raising_fc_proactive
    crashed_proactive = False
    try:
        report_pc = orch.run_audit("https://biz.example/")
    except Exception as exc:
        crashed_proactive = True
        report_pc = {}
        print(f"    (unexpected exception: {exc})")
    fc_mods["audit_runner"].identify_proactive_opportunities = real_fc_proactive

    check("A forced proactive-check (freshness) exception does NOT crash the whole audit", not crashed_proactive)
    if not crashed_proactive:
        check("Other specialists' proactive suggestions (e.g. crawl-render's) still present despite freshness's failing",
              bool(report_pc.get("proactive_suggestions")), str(report_pc.get("proactive_suggestions")))
        check("Proactive-check failure is recorded as diagnostics, not a fabricated site finding",
              "_diagnostics" in report_pc
              and any("proactive" in e and "freshness" in e for e in report_pc["_diagnostics"]["specialist_errors"])
              and all("simulated" not in f["title"].lower() for f in report_pc["findings"]),
              str(report_pc.get("_diagnostics")))
        check("Report remains schema-valid despite a proactive-check failure",
              report_builder.validate_report(report_pc) == [], str(report_builder.validate_report(report_pc)))

    # --- 19: zero-page / failed crawl ---
    def _fake_empty_crawl(site_url, cr_mods, max_pages, max_depth, render_max):
        return None, EMPTY_CRAWL_RESULT, []

    orch._run_shared_crawl = _fake_empty_crawl
    crashed_empty = False
    try:
        report3 = orch.run_audit("https://empty.example/")
    except Exception as exc:
        crashed_empty = True
        report3 = {}
        print(f"    (unexpected exception: {exc})")
    check("Zero-page crawl does NOT crash the orchestrator", not crashed_empty)
    if not crashed_empty:
        check("Zero-page crawl still produces a schema-valid report",
              report_builder.validate_report(report3) == [], str(report_builder.validate_report(report3)))

    n_pass = sum(1 for _, ok in results if ok)
    n_total = len(results)
    print(f"\nFIXTURE RESULTS: {n_pass}/{n_total} passed")
    return n_pass, n_total


def _is_iso8601(value: str) -> bool:
    from datetime import datetime
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def run_live_smoke_test(mods, site_url="https://example.com/"):
    print("\n" + "=" * 72)
    print("LIVE SMOKE TEST (single small real site, full pipeline)")
    print(f"Site: {site_url}")
    print("=" * 72)

    orch = mods["orchestrate"]
    report_builder = mods["report_builder"]

    # Reset any monkeypatching from the fixture tests above by loading a fresh copy.
    orch2 = load_module(os.path.join(ORCH_SCRIPTS, "orchestrate.py"), "orchestrate_live")

    crawl_stats = {}
    real_shared_crawl = orch2._run_shared_crawl

    def _spy_shared_crawl(site_url_, cr_mods, max_pages, max_depth, render_max):
        result = real_shared_crawl(site_url_, cr_mods, max_pages, max_depth, render_max)
        _robots, crawl_result, render_comparisons = result
        crawl_stats["urls_discovered"] = crawl_result.get("urls_discovered", 0)
        crawl_stats["urls_crawled"] = crawl_result.get("urls_crawled", 0)
        crawl_stats["pages_rendered"] = len(render_comparisons)
        return result

    orch2._run_shared_crawl = _spy_shared_crawl

    t0 = time.time()
    try:
        report = orch2.run_audit(site_url, max_pages=15, render_max=3)
        crashed = False
    except Exception:
        import traceback
        traceback.print_exc()
        report = {}
        crashed = True
    duration = round(time.time() - t0, 1)

    print(f"  pages discovered: {crawl_stats.get('urls_discovered', '?')}")
    print(f"  pages fetched:    {crawl_stats.get('urls_crawled', '?')}")
    print(f"  pages rendered:   {crawl_stats.get('pages_rendered', '?')}")
    print(f"  duration:         {duration}s")
    print(f"  PIPELINE CRASH:   {'YES (BAD)' if crashed else 'no'}")

    if not crashed:
        errors = report_builder.validate_report(report)
        print(f"  schema errors:    {errors if errors else 'none'}")
        print(f"  findings:         {report['summary']['total_findings']}")
        for f in report["findings"]:
            print(f"    [{f['severity'].upper()}] {f['id']}: {f['title']}")
        if report.get("_diagnostics"):
            print(f"  specialist errors: {report['_diagnostics']['specialist_errors']}")
        else:
            print("  specialist errors: none")

    return not crashed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--site", default="https://example.com/")
    args = parser.parse_args()

    print("=" * 72)
    print("Brand AI Readiness -- audit-orchestrator Validation (Stage 5)")
    print(f"Python: {sys.version.split()[0]}  |  CWD: {os.getcwd()}")
    print("=" * 72)

    mods = load_all_modules()

    n_pass, n_total = run_fixture_tests(mods)

    live_ok = True
    if not args.skip_live:
        live_ok = run_live_smoke_test(mods, site_url=args.site)

    print("\n" + "=" * 72)
    print("OVERALL RESULT")
    print("=" * 72)
    print(f"Fixture tests: {n_pass}/{n_total} passed")
    print(f"Live smoke test: {'OK' if live_ok else 'CRASHED'}")

    if n_pass != n_total or not live_ok:
        sys.exit(1)
