#!/usr/bin/env python3
"""
Phase 2 Validation Test Runner -- Real End-to-End Crawl/Render Audit

Run with project .venv:
    .venv\Scripts\python.exe validate_audit.py [url] [--no-render] [--max-pages N]
"""

from __future__ import annotations
import argparse, importlib.util, json, logging, os, sys, time
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# Real-world page content (headings, titles, names) can contain arbitrary Unicode.
# Windows consoles default to a legacy codepage (e.g. cp1252) that cannot encode much
# of it, which previously crashed printing mid-run on unrelated sites. Force UTF-8
# stdout/stderr so any site's content can be printed safely.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.join(os.path.dirname(__file__),
                    "brand-ai-readiness-audit","skills","crawl-render-audit","scripts")

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def load_all_modules():
    mods = {}
    for name in ["html_analysis","link_analysis","metadata_analysis",
                 "structured_data","robots_check","crawl","render"]:
        mods[name] = load_module(os.path.join(BASE,f"{name}.py"), name)
    ar_path = os.path.join(BASE,"audit_runner.py")
    with open(ar_path, encoding="utf-8") as f:
        src = f.read()
    for m in ["html_analysis","link_analysis","metadata_analysis","structured_data"]:
        src = src.replace(f"from .{m} import", f"from {m} import")
    tmp = os.path.join(BASE,"_ar_tmp.py")
    with open(tmp,"w",encoding="utf-8") as f:
        f.write(src)
    try:
        mods["audit_runner"] = load_module(tmp,"audit_runner")
    finally:
        if os.path.exists(tmp): os.remove(tmp)
    return mods

def run_pipeline(site_url, mods, max_pages=15, do_render=True, render_max=3):
    pw_ok = mods["render"].is_playwright_available()
    result = {
        "site": site_url,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "playwright_available": pw_ok,
        "robots": {}, "crawl": {},
        "render_detail": [], "render_comparisons": [],
        "render_skipped": not do_render or not pw_ok,
        "findings": [], "errors": [], "duration_s": 0.0,
    }
    t0 = time.time()

    # robots
    print(f"  [robots] fetching ...")
    try:
        robots_data = mods["robots_check"].fetch_robots_txt(site_url, timeout=10)
        result["robots"] = {"exists": robots_data.get("exists",False),
                            "sitemap_urls_count": len(robots_data.get("sitemap_urls",[])),
                            "error": robots_data.get("error")}
    except Exception as exc:
        result["robots"] = {"exists": False, "error": str(exc)}
        robots_data = None
        result["errors"].append(f"robots: {exc}")

    # crawl
    print(f"\n{'='*50}\nCRAWL START\nSite: {site_url}\nMax pages: {max_pages}\n{'='*50}")
    is_allowed = None
    if robots_data and robots_data.get("parser"):
        p = robots_data["parser"]
        is_allowed = lambda url: p.can_fetch("BrandAIReadinessAudit", url)
    try:
        crawl_result = mods["crawl"].bounded_crawl(
            site_url, is_allowed=is_allowed,
            max_pages=max_pages, max_depth=3, timeout=12)
    except Exception as exc:
        result["errors"].append(f"crawl: {exc}")
        crawl_result = {"pages":[],"sitemap_urls":[],"errors":[{"url":site_url,"error":str(exc)}],"urls_crawled":0,"urls_discovered":0}

    pages = crawl_result.get("pages",[])
    crawl_errors_list = crawl_result.get("errors",[])
    result["crawl"] = {
        "urls_discovered": crawl_result.get("urls_discovered",0),
        "urls_crawled": crawl_result.get("urls_crawled",0),
        "sitemap_urls_found": len(crawl_result.get("sitemap_urls",[])),
        "crawl_errors": len(crawl_errors_list),
        "crawl_error_details": crawl_errors_list[:5],
    }

    # Which pages will be attempted for rendering (mirrors the render step below).
    will_render = do_render and pw_ok and bool(pages)
    rendered_urls = {
        (p.get("final_url") or p.get("url")) for p in pages[:render_max]
    } if will_render else set()

    # Development-time crawl trace: one line per page so it's clear what was
    # actually fetched, its HTTP status, and whether it will be rendered.
    trace_rows = [(p.get("final_url") or p.get("url",""), p.get("status"), True,
                   (p.get("final_url") or p.get("url")) in rendered_urls) for p in pages]
    trace_rows += [(e.get("url",""), None, False, False) for e in crawl_errors_list]
    MAX_TRACE_ROWS = 30
    for i, (url, status, fetched, rendered) in enumerate(trace_rows[:MAX_TRACE_ROWS], 1):
        print(f"\n[{i}] {url}")
        print(f"    HTTP: {status if status is not None else 'n/a'}")
        print(f"    fetched: {'yes' if fetched else 'no'}")
        print(f"    rendered: {'yes' if rendered else 'no'}")
    if len(trace_rows) > MAX_TRACE_ROWS:
        print(f"\n... and {len(trace_rows) - MAX_TRACE_ROWS} more page(s) not shown.")
    print(f"\n{'='*50}")
    print("CRAWL COMPLETE")
    print(f"Pages discovered: {result['crawl']['urls_discovered']}")
    print(f"Pages fetched:    {len(pages)}")
    print(f"Pages rendered:   {len(rendered_urls)}")
    print(f"{'='*50}")

    # render
    render_comparisons = []
    render_detail = []
    if do_render and pw_ok and pages:
        urls_to_render = [p.get("final_url") or p.get("url") for p in pages[:render_max]]
        print(f"  [render] rendering {len(urls_to_render)} page(s) with Playwright ...")
        try:
            import bs4 as _bs4
            rendered_results = mods["render"].render_multiple_pages(urls_to_render, timeout_ms=25000)
            for page_data, rdata in zip(pages[:render_max], rendered_results):
                url = page_data.get("final_url") or page_data.get("url","")
                raw_html = page_data.get("body","")
                err = rdata.get("error")
                try:
                    raw_text = mods["html_analysis"].extract_visible_text(raw_html)
                    raw_headings = mods["html_analysis"].extract_headings(
                        _bs4.BeautifulSoup(raw_html,"html.parser"))
                except Exception:
                    raw_text=""; raw_headings={}
                det = {
                    "url": url,
                    "raw_html_length": len(raw_html),
                    "raw_text_length": len(raw_text),
                    "rendered_text_length": rdata.get("rendered_text_length"),
                    "render_error": err,
                    "playwright_available": rdata.get("playwright_available", True),
                }
                if not err:
                    rt = rdata.get("rendered_text") or ""
                    rh = rdata.get("rendered_headings",{})
                    comp = mods["render"].compare_raw_vs_rendered(raw_text, rt, raw_headings, rh)
                    comp["url"] = url
                    comp["missing_headings"] = comp.get("headings_only_in_rendered",[])
                    det.update({
                        "content_difference_ratio": comp.get("content_difference_ratio",0),
                        "significant_gap": comp.get("significant_gap",False),
                        "js_dependent": comp.get("js_dependent",False),
                        "loading_placeholder": comp.get("loading_placeholder_detected",False),
                        "headings_only_in_rendered": comp.get("headings_only_in_rendered",[]),
                    })
                    render_comparisons.append(comp)
                else:
                    det.update({"content_difference_ratio":None,"significant_gap":False,"js_dependent":False})
                render_detail.append(det)
            ok = sum(1 for d in render_detail if not d.get("render_error"))
            print(f"  [render] {ok}/{len(render_detail)} pages rendered OK")
        except Exception as exc:
            result["errors"].append(f"render: {exc}")
            print(f"  [render] FAILED: {exc}")
            import traceback; traceback.print_exc()
    elif not pw_ok:
        print("  [render] SKIPPED -- Playwright not available")
    else:
        print("  [render] SKIPPED -- disabled")

    result["render_detail"] = render_detail
    result["render_comparisons"] = [
        {"url": rc.get("url",""), "raw_len": rc.get("raw_text_length",0),
         "rendered_len": rc.get("rendered_text_length",0),
         "ratio": rc.get("content_difference_ratio",0),
         "significant_gap": rc.get("significant_gap",False),
         "missing_headings": rc.get("missing_headings",[])}
        for rc in render_comparisons
    ]

    # audit
    print(f"  [audit] C1-C12 ...")
    try:
        findings = mods["audit_runner"].run_crawl_audit(
            crawl_result, robots_data=robots_data,
            render_comparisons=render_comparisons if render_comparisons else None)
    except Exception as exc:
        result["errors"].append(f"audit_runner: {exc}")
        findings = []
        import traceback; traceback.print_exc()

    result["findings"] = findings
    result["duration_s"] = round(time.time()-t0, 1)
    by_sev = {"critical":0,"high":0,"medium":0,"low":0}
    by_cat = {}
    for f in findings:
        s = f.get("severity","medium"); by_sev[s] = by_sev.get(s,0)+1
        c = f.get("category","?"); by_cat[c] = by_cat.get(c,0)+1
    result["summary"] = {"total_findings":len(findings),"by_severity":by_sev,"by_category":by_cat}
    return result

def validate_schema(f):
    errs = []
    for field in ("title","severity","category","evidence","suggested_action"):
        if field not in f: errs.append(f"missing:{field}")
    sa = f.get("suggested_action",{})
    if not isinstance(sa,dict): errs.append("sa not dict")
    else:
        for sf in ("summary","priority"):
            if sf not in sa: errs.append(f"sa.missing:{sf}")
    if f.get("severity") not in ("critical","high","medium","low"):
        errs.append(f"bad severity:{f.get('severity')}")
    return errs

def print_result(site, r):
    pw = "YES" if r.get("playwright_available") else "NO"
    print(f"\n{'='*72}")
    print(f"SITE: {site}")
    print(f"{'='*72}")
    print(f"  Duration:         {r['duration_s']}s  |  Playwright: {pw}")
    rob = r["robots"]
    rob_s = "EXISTS" if rob.get("exists") else "MISSING"
    if rob.get("error"): rob_s += f" ({rob['error']})"
    print(f"  robots.txt:       {rob_s}")
    crawl = r.get("crawl",{})
    print(f"  URLs discovered:  {crawl.get('urls_discovered','?')}")
    print(f"  Pages crawled:    {crawl.get('urls_crawled','?')}  |  Sitemap URLs: {crawl.get('sitemap_urls_found','?')}")
    if crawl.get("crawl_error_details"):
        for ce in crawl["crawl_error_details"][:3]:
            print(f"    crawl error: {ce.get('url','?')}: {ce.get('error','?')}")
    print()

    rds = r.get("render_detail",[])
    print(f"  C4 / RENDER DETAIL  ({len(rds)} page(s) attempted):")
    if not rds:
        print(f"    (render not performed)")
    for rd in rds:
        url = rd.get("url","?")[:65]
        err = rd.get("render_error")
        print(f"    [{url}]")
        print(f"      raw HTML chars:      {rd.get('raw_html_length',0):,}")
        print(f"      raw text chars:      {rd.get('raw_text_length',0):,}")
        if err:
            print(f"      render error:        {err}")
        else:
            print(f"      rendered text chars: {rd.get('rendered_text_length',0):,}")
            ratio = rd.get("content_difference_ratio",0)
            sig = rd.get("significant_gap",False)
            jsd = rd.get("js_dependent",False)
            ph = rd.get("loading_placeholder",False)
            print(f"      diff ratio:          {ratio:.3f}  |  significant_gap={sig}  |  js_dependent={jsd}  |  placeholder={ph}")
            h_only = rd.get("headings_only_in_rendered",[])
            if h_only:
                print(f"      headings only rendered: {h_only[:5]}")

    findings = r.get("findings",[])
    summary = r.get("summary",{})
    by_sev = summary.get("by_severity",{})
    print(f"\n  TOTAL FINDINGS: {summary.get('total_findings',0)}")
    print(f"  CRITICAL={by_sev.get('critical',0)}  HIGH={by_sev.get('high',0)}  MEDIUM={by_sev.get('medium',0)}  LOW={by_sev.get('low',0)}")
    print(f"  By category: {summary.get('by_category',{})}")
    if findings:
        print()
        for i,f in enumerate(findings,1):
            cat=f.get("category","?"); sev=f.get("severity","?").upper()
            title=f.get("title","?"); ev=f.get("evidence","").replace("\n"," ")[:240]
            sa=f.get("suggested_action",{})
            se=validate_schema(f)
            print(f"    F-{i:03d} [{sev}] {cat}: {title}")
            print(f"           Evidence: {ev}")
            print(f"           Action:   {sa.get('summary','')[:110]}")
            if se: print(f"           SCHEMA ERR: {se}")
    if r.get("errors"):
        print(f"\n  PIPELINE ERRORS: {r['errors']}")

def print_summary(results):
    print("\n"+"="*82)
    print("SUMMARY TABLE")
    print("="*82)
    print(f"{'Website':<35} {'Pages':>6} {'Rend':>5} {'Runtime':>8} {'Findings':>9} {'C/H/M/L':>12} {'E':>3}")
    print("-"*82)
    for site,r in results:
        c=r.get("crawl",{}); pages=c.get("urls_crawled",0)
        rend=len(r.get("render_detail",[])); rt=f"{r.get('duration_s',0)}s"
        tot=r.get("summary",{}).get("total_findings",0)
        bs=r.get("summary",{}).get("by_severity",{})
        ss=f"{bs.get('critical',0)}/{bs.get('high',0)}/{bs.get('medium',0)}/{bs.get('low',0)}"
        errs=len(r.get("errors",[])); ss2=site.replace("https://","").replace("http://","")[:35]
        print(f"{ss2:<35} {pages:>6} {rend:>5} {rt:>8} {tot:>9} {ss:>12} {errs:>3}")
    print("="*82)

def test_errors(mods):
    print("\n"+"="*72+"\nERROR HANDLING TESTS\n"+"="*72)
    tests = [
        ("A. Invalid URL",      "not-a-valid-url"),
        ("B. Nonexistent domain","https://xyz-doesnotexist-999.com"),
    ]
    for label, url in tests:
        try:
            r = run_pipeline(url, mods, max_pages=1, do_render=False)
            errs=r.get("errors",[]); finds=r.get("summary",{}).get("total_findings",0)
            print(f"  {label}: HANDLED -> errors={errs[:1]}, findings={finds}")
        except Exception as e:
            print(f"  {label}: UNHANDLED EXCEPTION (bad) -> {e}")

    # Malformed HTML
    m = {"pages":[{"url":"https://t.com/","final_url":"https://t.com/","status":200,
         "body":"<html><head><title>T</title><body><h1>T","headers":{"content-type":"text/html"},
         "redirects":[],"response_time_ms":100,"error":None,"depth":0}],
         "sitemap_urls":[],"urls_discovered":1,"urls_crawled":1,"errors":[]}
    try:
        fs = mods["audit_runner"].run_crawl_audit(m)
        print(f"  C. Malformed HTML:    HANDLED -> {len(fs)} findings")
    except Exception as e:
        print(f"  C. Malformed HTML:    UNHANDLED EXCEPTION (bad) -> {e}")

    # Malformed JSON-LD
    bj = {"pages":[{"url":"https://t.com/product","final_url":"https://t.com/product","status":200,
         "body":'<html><head><title>P</title><script type="application/ld+json">{bad!!!</script></head><body><h1>P</h1><p>Content.</p></body></html>',
         "headers":{"content-type":"text/html"},"redirects":[],"response_time_ms":100,"error":None,"depth":0}],
         "sitemap_urls":["https://t.com/product"],"urls_discovered":1,"urls_crawled":1,"errors":[]}
    try:
        fs = mods["audit_runner"].run_crawl_audit(bj)
        print(f"  D. Malformed JSON-LD: HANDLED -> {len(fs)} findings")
    except Exception as e:
        print(f"  D. Malformed JSON-LD: UNHANDLED EXCEPTION (bad) -> {e}")

def test_c7_js_heavy_gating(mods):
    """Stage 7 regression: C7 must not flag structured-data-vs-visible-text
    'inconsistencies' on a page whose raw HTML is known (via render_comparisons)
    to be substantially incomplete due to JS rendering -- confirmed as a real
    false positive on a JS-heavy unseen site. A genuine mismatch on an
    ordinary (non-JS-heavy) page must still be caught.
    """
    print("\n" + "=" * 72 + "\nC7 JS-HEAVY GATING (Stage 7 regression)\n" + "=" * 72)
    js_heavy_url = "https://t.com/js-heavy"
    normal_url = "https://t.com/normal"
    crawl_result = {
        "pages": [
            {"url": js_heavy_url, "final_url": js_heavy_url, "status": 200,
             "body": '<html><head><title>App</title><script type="application/ld+json">'
                     '{"@type":"Organization","name":"Acme Gadgets","description":"We sell gadgets."}'
                     '</script></head><body><div id="root"></div></body></html>',
             "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": 1},
            {"url": normal_url, "final_url": normal_url, "status": 200,
             "body": '<html><head><title>Home</title><script type="application/ld+json">'
                     '{"@type":"Organization","name":"Wrong Name Inc"}</script></head>'
                     '<body><h1>Totally Different Company</h1>'
                     '<p>Totally Different Company is the leading provider of widgets in the region, '
                     'serving customers since 2001 with a wide range of widget products and services.</p>'
                     '</body></html>',
             "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": 1},
        ],
        "sitemap_urls": [], "urls_discovered": 2, "urls_crawled": 2, "errors": [],
    }
    render_comparisons = [
        {"url": js_heavy_url, "raw_text_length": 5, "rendered_text_length": 2000,
         "content_difference_ratio": 0.99, "significant_gap": True},
        {"url": normal_url, "raw_text_length": 200, "rendered_text_length": 205,
         "content_difference_ratio": 0.0, "significant_gap": False},
    ]
    findings = mods["audit_runner"].run_crawl_audit(crawl_result, render_comparisons=render_comparisons)
    c7 = [f for f in findings if f.get("category") == "C7"]
    evidence_blob = " ".join(f.get("evidence", "") for f in c7)
    js_heavy_flagged = js_heavy_url in evidence_blob
    normal_flagged = normal_url in evidence_blob
    status_a = "PASS" if not js_heavy_flagged else "FAIL"
    status_b = "PASS" if normal_flagged else "FAIL"
    print(f"  [{status_a}] JS-heavy page NOT flagged by C7 (raw HTML known incomplete)")
    print(f"  [{status_b}] Normal page WITH a genuine name mismatch still flagged by C7")
    if status_a == "FAIL" or status_b == "FAIL":
        print(f"    C7 findings: {c7}")
    return status_a == "PASS" and status_b == "PASS"


def test_c6_http_error_gating(mods):
    """Hardening regression: C6 must not recommend structured data for an
    HTTP error page (4xx/5xx) -- confirmed as a real false positive on a
    real unseen site (a 404 page was recommended Product/Offer schema).
    A genuine 200 page missing schema must still be flagged.
    """
    print("\n" + "=" * 72 + "\nC6 HTTP-ERROR GATING (hardening regression)\n" + "=" * 72)

    def _page(url, status):
        return {"url": url, "final_url": url, "status": status,
                "body": '<html><head><title>Product</title></head><body><h1>Widget Pro</h1><p>Buy our product.</p></body></html>',
                "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": 1}

    scenarios = [
        ("200 product page without schema -> C6 SHOULD fire", "https://t.com/product/widget", 200, True),
        ("200 organization/about page without schema -> C6 SHOULD fire", "https://t.com/about/company", 200, True),
        ("404 page without schema -> C6 should NOT fire", "https://t.com/product/missing", 404, False),
        ("500 page without schema -> C6 should NOT fire", "https://t.com/product/broken", 500, False),
    ]
    all_ok = True
    for label, url, status, should_fire in scenarios:
        crawl_result = {
            "pages": [_page(url, status)],
            "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
        }
        findings = mods["audit_runner"].run_crawl_audit(crawl_result)
        c6 = [f for f in findings if f.get("category") == "C6"]
        fired = any(url in f.get("evidence", "") for f in c6)
        ok = fired == should_fire
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"    C6 findings: {c6}")
    return all_ok


def test_proactive_sitemap_opportunities(mods):
    """Part 1 (proactive suggestions) regression: P1/P2 sitemap opportunities.

    P1: sitemap exists (default location) but robots.txt doesn't reference it.
    P2: no sitemap found via either path.
    Neither should fire when the sitemap IS properly referenced.
    """
    print("\n" + "=" * 72 + "\nPROACTIVE P1/P2 -- SITEMAP OPPORTUNITIES\n" + "=" * 72)
    fn = mods["audit_runner"].identify_proactive_opportunities
    all_ok = True

    def _check(label, condition, detail=""):
        nonlocal all_ok
        all_ok = all_ok and condition
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if not condition and detail:
            print(f"    {detail}")

    # P1: sitemap exists, robots.txt exists but has no Sitemap: directive.
    cr = {"sitemap_urls": ["https://t.com/a", "https://t.com/b"], "pages": [], "errors": []}
    rd = {"exists": True, "sitemap_urls": []}
    opp = fn(cr, rd)
    _check("P1 fires: sitemap found, robots.txt exists but doesn't reference it",
           any("robots.txt" in o["title"].lower() or "not referenced" in o["title"].lower()
               or "isn't referenced" in o["title"] for o in opp), str(opp))
    _check("P1 entry has no 'severity' field (not a defect)", opp and "severity" not in opp[0], str(opp))

    # Sitemap exists AND is referenced -> neither P1 nor P2 should fire.
    cr2 = {"sitemap_urls": ["https://t.com/a"], "pages": [], "errors": []}
    rd2 = {"exists": True, "sitemap_urls": ["https://t.com/sitemap.xml"]}
    opp2 = fn(cr2, rd2)
    _check("Neither P1 nor P2 fires when sitemap is properly referenced", opp2 == [], str(opp2))

    # P2: no sitemap found anywhere.
    cr3 = {"sitemap_urls": [], "pages": [], "errors": []}
    rd3 = {"exists": True, "sitemap_urls": []}
    opp3 = fn(cr3, rd3)
    _check("P2 fires: no sitemap found via robots.txt or default location",
           any("no sitemap" in o["title"].lower() for o in opp3), str(opp3))

    # P2 should also fire gracefully when robots.txt itself doesn't exist.
    cr4 = {"sitemap_urls": [], "pages": [], "errors": []}
    rd4 = {"exists": False, "sitemap_urls": [], "error": "HTTP 404"}
    opp4 = fn(cr4, rd4)
    _check("P2 fires even when robots.txt itself is missing", any("no sitemap" in o["title"].lower() for o in opp4), str(opp4))

    return all_ok


# ---------------------------------------------------------------------------
# Part 2 (Suggested Action Sophistication) regression: suggested_action
# text quality across all C1-C12 detectors.
# ---------------------------------------------------------------------------

_BOILERPLATE_ACTIONS = {
    "fix this issue.", "review and fix the problem.", "improve seo.",
    "update the page accordingly.", "investigate and resolve.", "ensure this is correct.",
}


class _FakeRobotsParser:
    """Minimal stand-in for a robots.txt parser: blocks exactly one URL."""
    def __init__(self, blocked_url):
        self.blocked_url = blocked_url

    def can_fetch(self, agent, url):
        return url != self.blocked_url


def _page_fixture(url, status=200, body="", depth=1, redirects=None):
    return {"url": url, "final_url": url, "status": status, "body": body,
            "headers": {}, "redirects": redirects or [], "response_time_ms": 10,
            "error": None, "depth": depth}


def test_suggested_action_quality(mods):
    """Part 2 regression: every C1-C12 suggested_action is non-empty, not
    generic boilerplate, and mentions remediation content specific to that
    detector. Detection/severity/evidence logic is untouched by Part 2 --
    this only verifies the upgraded suggested_action TEXT.
    """
    print("\n" + "=" * 72 + "\nPART 2 -- SUGGESTED ACTION QUALITY (C1-C12)\n" + "=" * 72)
    ar = mods["audit_runner"]
    all_ok = True
    by_category: dict[str, list[dict]] = {}

    def _collect(findings):
        for f in findings:
            by_category.setdefault(f.get("category"), []).append(f)

    # --- Scenario A: C1 (robots.txt block) + C8 (noindex) ---
    robots_data_a = {"exists": True, "parser": _FakeRobotsParser("https://acme.example/product/blocked-item")}
    cr_a = {
        "pages": [
            _page_fixture("https://acme.example/", depth=0, body="<html><body><h1>Acme</h1><p>Home.</p></body></html>"),
            _page_fixture("https://acme.example/product/blocked-item",
                          body="<html><body><h1>Widget</h1><p>Buy our widget today.</p></body></html>"),
            _page_fixture("https://acme.example/about/blocked-about",
                          body='<html><head><meta name="robots" content="noindex"></head>'
                               '<body><h1>About</h1><p>About our company and its history.</p></body></html>'),
        ],
        "sitemap_urls": [], "urls_discovered": 3, "urls_crawled": 3, "errors": [],
    }
    _collect(ar.run_crawl_audit(cr_a, robots_data=robots_data_a))

    # --- Scenario B: C2 (HTTP error) + C3 (redirect loop + long chain) ---
    cr_b = {
        "pages": [
            _page_fixture("https://acme.example/", depth=0, body="<html><body><h1>Acme</h1><p>Home.</p></body></html>"),
            _page_fixture("https://acme.example/product/broken", status=404, body="Not found"),
            _page_fixture("https://acme.example/contact", redirects=[
                {"url": "https://acme.example/contact"}, {"url": "https://acme.example/contact-alt"},
            ]),
            _page_fixture("https://acme.example/pricing", redirects=[
                {"url": "https://acme.example/pricing"}, {"url": "https://acme.example/pricing/v2"},
                {"url": "https://acme.example/pricing/v3"}, {"url": "https://acme.example/pricing/v4"},
            ]),
        ],
        "sitemap_urls": [], "urls_discovered": 4, "urls_crawled": 4, "errors": [],
    }
    _collect(ar.run_crawl_audit(cr_b))

    # --- Scenario C: reuse the proven C4/C7 fixture from the JS-heavy regression test ---
    js_heavy_url = "https://acme.example/product/appview"
    normal_url = "https://acme.example/product/normal"
    cr_c = {
        "pages": [
            _page_fixture(js_heavy_url, body='<html><head><title>App</title><script type="application/ld+json">'
                          '{"@type":"Organization","name":"Acme Gadgets","description":"We sell gadgets."}'
                          '</script></head><body><div id="root"></div></body></html>'),
            _page_fixture(normal_url, body='<html><head><title>Home</title><script type="application/ld+json">'
                          '{"@type":"Organization","name":"Wrong Name Inc"}</script></head>'
                          '<body><h1>Totally Different Company</h1>'
                          '<p>Totally Different Company is the leading provider of widgets in the region, '
                          'serving customers since 2001 with a wide range of widget products and services.</p>'
                          '</body></html>'),
        ],
        "sitemap_urls": [], "urls_discovered": 2, "urls_crawled": 2, "errors": [],
    }
    render_comparisons_c = [
        {"url": js_heavy_url, "raw_text_length": 5, "rendered_text_length": 2000,
         "content_difference_ratio": 0.99, "significant_gap": True},
        {"url": normal_url, "raw_text_length": 200, "rendered_text_length": 205,
         "content_difference_ratio": 0.0, "significant_gap": False},
    ]
    _collect(ar.run_crawl_audit(cr_c, render_comparisons=render_comparisons_c))

    # --- Scenario D: C6 (missing structured data), reusing the proven C6 fixture ---
    cr_d = {
        "pages": [_page_fixture("https://acme.example/product/widget",
                  body='<html><head><title>Product</title></head><body><h1>Widget Pro</h1>'
                       '<p>Buy our product.</p></body></html>')],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    _collect(ar.run_crawl_audit(cr_d))

    # --- Scenario E: C5 (canvas), C9 (orphans/disconnected), C10 (canonical),
    # C11 (missing title), C12 (missing H1 / multiple H1) -- none of these
    # extra pages are linked from the homepage, so all become C9 orphans too;
    # that's expected and doesn't interfere with the other checks.
    long_text = " ".join(["This page has substantial real content about the topic."] * 6)
    cr_e = {
        "pages": [
            _page_fixture("https://acme.example/", depth=0,
                           body='<html><body><h1>Acme</h1><a href="/product/a">A</a></body></html>'),
            _page_fixture("https://acme.example/product/a",
                           body=f"<html><head><title>Product A</title></head><body><h1>Product A</h1><p>{long_text}</p></body></html>"),
            _page_fixture("https://acme.example/product/canvasitem",
                           body='<html><body><canvas></canvas><p>Buy now.</p></body></html>'),
            _page_fixture("https://acme.example/product/canonical-issue",
                           body='<html><head><link rel="canonical" href="https://acme.example/product/other-page">'
                                f'<title>Canonical Issue</title></head><body><h1>Canonical Issue</h1><p>{long_text}</p></body></html>'),
            _page_fixture("https://acme.example/product/no-title",
                           body=f"<html><head></head><body><h1>No Title Page</h1><p>{long_text}</p></body></html>"),
            _page_fixture("https://acme.example/product/no-h1",
                           body=f"<html><head><title>No H1 Page</title></head><body><p>{long_text}</p></body></html>"),
            _page_fixture("https://acme.example/product/multi-h1",
                           body=f"<html><head><title>Multi H1 Page</title></head><body><h1>First</h1><h1>Second</h1><p>{long_text}</p></body></html>"),
        ],
        "sitemap_urls": [], "urls_discovered": 7, "urls_crawled": 7, "errors": [],
    }
    _collect(ar.run_crawl_audit(cr_e))

    _EXPECTED_KEYWORDS = {
        "C1": ["disallow"],
        "C2": ["http 200"],
        "C3": ["hop"],  # covers both "single hop" (loop) and "one hop" (long chain)
        "C4": ["ssr"],
        "C5": ["alt text"],
        "C6": ["json-ld"],
        "C7": ["name", "description", "price", "availability"],  # either sub-type's keywords
        "C8": ["noindex"],
        "C9": ["link"],  # covers "inbound link" (orphans) and "link path"/"link chain" (disconnected)
        "C10": ["canonical"],
        "C11": ["title"],
        "C12": ["h1"],
    }

    def _check(label, condition, detail=""):
        nonlocal all_ok
        all_ok = all_ok and condition
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if not condition and detail:
            print(f"    {detail}")

    for category, expected_keywords in _EXPECTED_KEYWORDS.items():
        findings = by_category.get(category, [])
        _check(f"{category}: at least one finding was produced by the fixture", bool(findings), str(findings))
        for f in findings:
            summary = f.get("suggested_action", {}).get("summary", "")
            title = f.get("title", "")[:60]
            normalized = " ".join(summary.strip().lower().split())
            _check(f"{category} ({title}): suggested_action is non-empty", bool(normalized), summary)
            _check(f"{category} ({title}): suggested_action is not generic boilerplate",
                   normalized not in _BOILERPLATE_ACTIONS, summary)
            _check(f"{category} ({title}): suggested_action mentions detector-relevant remediation content",
                   any(kw in normalized for kw in expected_keywords), summary)

    return all_ok


def test_c10_canonical_reliability(mods):
    """Final hardening regression: C10 relative-canonical resolution (Fix 1)
    and bounded-crawl reliability guard (Fix 2). Synthetic, domain-neutral
    fixtures only (example.test / other.example).
    """
    print("\n" + "=" * 72 + "\nC10 CANONICAL RELIABILITY (final hardening)\n" + "=" * 72)
    ar = mods["audit_runner"]
    all_ok = True

    def _check(label, condition, detail=""):
        nonlocal all_ok
        all_ok = all_ok and condition
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if not condition and detail:
            print(f"    {detail}")

    def _c10_findings(findings):
        return [f for f in findings if f.get("category") == "C10"]

    def _body(canonical_href=None, h1="Page"):
        head = f'<link rel="canonical" href="{canonical_href}">' if canonical_href else ""
        return f"<html><head>{head}</head><body><h1>{h1}</h1><p>Some real page content here.</p></body></html>"

    # --- Case A: relative same-domain canonical (self-reference) ---
    cr_a = {
        "pages": [_page_fixture("https://example.test/about", body=_body("/about"))],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    findings_a = _c10_findings(ar.run_crawl_audit(cr_a))
    _check("Case A: relative same-domain canonical NOT misclassified as cross-domain",
           findings_a == [], str(findings_a))

    # --- Case B: relative canonical with query string ---
    cr_b = {
        "pages": [_page_fixture("https://example.test/privacy", body=_body("/privacy?lang=en"))],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    findings_b = _c10_findings(ar.run_crawl_audit(cr_b))
    _check("Case B: relative canonical with query string resolves correctly (no false cross-domain)",
           findings_b == [], str(findings_b))

    # --- Case C: absolute same-domain canonical (self-reference) -- unchanged behavior ---
    cr_c = {
        "pages": [_page_fixture("https://example.test/about", body=_body("https://example.test/about"))],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    findings_c = _c10_findings(ar.run_crawl_audit(cr_c))
    _check("Case C: absolute same-domain self-referencing canonical still produces no finding",
           findings_c == [], str(findings_c))

    # --- Case D: genuine cross-domain canonical -- must still fire unconditionally ---
    cr_d = {
        "pages": [_page_fixture("https://example.test/about", body=_body("https://other.example/about"))],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    findings_d = _c10_findings(ar.run_crawl_audit(cr_d))
    _check("Case D: genuine cross-domain canonical still detected",
           any("cross-domain" in f["evidence"].lower() for f in findings_d), str(findings_d))

    # --- Case E: same-domain canonical target outside the bounded crawl, LOW coverage -> must NOT fire ---
    low_coverage_sitemap = [f"https://example.test/other-page-{i}" for i in range(20)]
    cr_e = {
        "pages": [_page_fixture("https://example.test/page-x", body=_body("/page-y"))],
        "sitemap_urls": low_coverage_sitemap, "urls_discovered": 21, "urls_crawled": 1, "errors": [],
    }
    findings_e = _c10_findings(ar.run_crawl_audit(cr_e))
    _check("Case E: same-domain canonical target outside a LOW-coverage bounded crawl NOT flagged",
           findings_e == [], str(findings_e))

    # --- Case F: same scenario, but HIGH coverage -> genuine problem still detected ---
    cr_f = {
        "pages": [_page_fixture("https://example.test/page-x", body=_body("/page-y"))],
        "sitemap_urls": [], "urls_discovered": 1, "urls_crawled": 1, "errors": [],
    }
    findings_f = _c10_findings(ar.run_crawl_audit(cr_f))
    _check("Case F: same-domain canonical target missing under HIGH crawl coverage still flagged",
           any("not found in crawled pages" in f["evidence"].lower() for f in findings_f), str(findings_f))

    # --- Case G: normal small site with correct self-referencing canonicals -> guard doesn't cause a false finding ---
    cr_g = {
        "pages": [
            _page_fixture("https://example.test/", body=_body("https://example.test/"), depth=0),
            _page_fixture("https://example.test/about", body=_body("https://example.test/about")),
        ],
        "sitemap_urls": [], "urls_discovered": 2, "urls_crawled": 2, "errors": [],
    }
    findings_g = _c10_findings(ar.run_crawl_audit(cr_g))
    _check("Case G: normal small site with correct self-referencing canonicals produces no finding",
           findings_g == [], str(findings_g))

    # --- Case H (final hardening): canonical points to ANOTHER already-crawled
    # page via an /index.html-equivalent alias (e.g. the crawled homepage is
    # "https://example.test/3/" and an old-version page's canonical is
    # "https://example.test/3/index.html") -- these are the same logical page
    # and must NOT be flagged, even though it's a different page's canonical,
    # not a self-reference.
    cr_h = {
        "pages": [
            _page_fixture("https://example.test/3/", body=_body("https://example.test/3/"), depth=0),
            _page_fixture("https://example.test/3.11/", body=_body("https://example.test/3/index.html")),
        ],
        "sitemap_urls": [], "urls_discovered": 2, "urls_crawled": 2, "errors": [],
    }
    findings_h = _c10_findings(ar.run_crawl_audit(cr_h))
    _check("Case H: canonical pointing to another crawled page via an /index.html-equivalent alias NOT flagged",
           findings_h == [], str(findings_h))

    return all_ok


TEST_SITES = [
    ("Static (example.com)",           "https://example.com",            5),
    ("Docs (docs.python.org)",          "https://docs.python.org/3/",    15),
    ("Corporate (nginx.org)",           "https://nginx.org/",            10),
    ("Aggregator (news.ycombinator)",   "https://news.ycombinator.com/", 10),
    ("JS-SPA (vuejs.org)",              "https://vuejs.org/",             5),
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?")
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--render-max", type=int, default=3)
    parser.add_argument("--error-tests", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    do_render = not args.no_render

    print("="*72)
    print("Brand AI Readiness -- crawl-render-audit Validation")
    print(f"Python: {sys.version.split()[0]}  |  CWD: {os.getcwd()}")
    print("="*72)
    print("\nLoading modules ...")
    mods = load_all_modules()
    pw = mods["render"].is_playwright_available()
    print(f"Playwright: {'AVAILABLE' if pw else 'NOT AVAILABLE'}")

    if args.error_tests:
        test_errors(mods)
        c7_ok = test_c7_js_heavy_gating(mods)
        if not c7_ok:
            print("\nC7 JS-heavy gating regression test FAILED")
        c6_ok = test_c6_http_error_gating(mods)
        if not c6_ok:
            print("\nC6 HTTP-error gating regression test FAILED")
        p1p2_ok = test_proactive_sitemap_opportunities(mods)
        if not p1p2_ok:
            print("\nProactive P1/P2 sitemap opportunities test FAILED")
        action_quality_ok = test_suggested_action_quality(mods)
        if not action_quality_ok:
            print("\nPart 2 suggested_action quality test FAILED")
        c10_ok = test_c10_canonical_reliability(mods)
        if not c10_ok:
            print("\nC10 canonical reliability regression test FAILED")

    sites = [("User URL", args.url, args.max_pages)] if args.url else TEST_SITES
    all_results = []
    for label, url, max_p in sites:
        mp = args.max_pages if args.url else max_p
        print(f"\n{'='*72}")
        print(f"AUDITING: {label}  URL: {url}  max_pages: {mp}  render: {do_render}")
        print(f"{'='*72}")
        try:
            r = run_pipeline(url, mods, max_pages=mp, do_render=do_render, render_max=args.render_max)
            print_result(url, r)
            all_results.append((url, r))
        except Exception as exc:
            print(f"  PIPELINE EXCEPTION: {exc}")
            import traceback; traceback.print_exc()
            all_results.append((url,{"errors":[str(exc)],"summary":{"total_findings":0,"by_severity":{},"by_category":{}},"crawl":{},"robots":{},"findings":[],"render_detail":[],"duration_s":0}))

    print_summary(all_results)
    if args.output:
        with open(args.output,"w",encoding="utf-8") as f:
            json.dump({s:r for s,r in all_results},f,indent=2,ensure_ascii=False,default=str)
        print(f"\nSaved -> {args.output}")
    print("\nDone.")
