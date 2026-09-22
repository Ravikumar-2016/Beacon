#!/usr/bin/env python3
r"""
Stage 4 Validation Test Runner -- Engagement Audit

Same two-part approach as Stage 3:
  1. Deterministic fixture tests against LOCAL, CONTROLLED HTML (no network;
     E11's viewport checks use a local file:// URL so they still exercise a
     real browser without any network dependency).
  2. One small real-site smoke test (https://example.com by default).

Run with the project .venv:
    .venv\Scripts\python.exe validate_engagement_audit.py [--skip-live]
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(__file__)
EA_BASE = os.path.join(ROOT, "brand-ai-readiness-audit", "skills", "engagement-audit", "scripts")
CR_BASE = os.path.join(ROOT, "brand-ai-readiness-audit", "skills", "crawl-render-audit", "scripts")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_all_modules():
    mods = {}
    for name in ["page_orientation", "navigation_analysis", "cta_analysis", "link_health",
                 "viewport_check", "engagement_analysis"]:
        mods[name] = load_module(os.path.join(EA_BASE, f"{name}.py"), name)

    ar_path = os.path.join(EA_BASE, "audit_runner.py")
    with open(ar_path, encoding="utf-8") as f:
        src = f.read()
    for m in ["page_orientation", "navigation_analysis", "cta_analysis", "link_health",
              "viewport_check", "engagement_analysis"]:
        src = src.replace(f"from .{m} import", f"from {m} import")
    tmp = os.path.join(EA_BASE, "_ea_ar_tmp.py")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        mods["audit_runner"] = load_module(tmp, "engagement_audit_runner")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    mods["crawl"] = load_module(os.path.join(CR_BASE, "crawl.py"), "cr_crawl")
    mods["robots_check"] = load_module(os.path.join(CR_BASE, "robots_check.py"), "cr_robots_check")
    return mods


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _page(url, status, body, depth=1):
    return {"url": url, "final_url": url, "status": status, "body": body,
            "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": depth}


def crawl_result_of(*pages):
    return {"pages": list(pages), "sitemap_urls": [], "urls_discovered": len(pages),
            "urls_crawled": len(pages), "errors": []}


# --- E1: orientation ---
CR_E1_MISSING = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header></header></body></html>", depth=0),
                                 _page("https://biz.example/product/widget", 200, "<html><body><p>Some text with no heading at all here.</p></body></html>"))
CR_E1_GOOD = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                              _page("https://biz.example/product/widget", 200,
                                    "<html><body><h1>Widget Pro</h1><p>The best widget.</p></body></html>"))

# --- E2/E8: CTA quality ---
CR_E2_NO_CTA = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                _page("https://biz.example/pricing", 200,
                                      "<html><body><h1>Pricing</h1><p>Plans start at $10/mo.</p></body></html>"))
CR_E8_GENERIC_ONLY = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                      _page("https://biz.example/product/widget", 200,
                                            "<html><body><h1>Widget</h1><a class='btn' href='/more'>Learn More</a></body></html>"))
CR_GOOD_CTA = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                               _page("https://biz.example/product/widget", 200,
                                     "<html><body><h1>Widget</h1><a class='btn' href='/trial'>Start Free Trial</a></body></html>"))

# --- E12: unique-element counting (hardening regression) ---
# A: one element whose class matches FOUR keywords at once -> one signal.
CR_E12_OVERLAPPING_CLASSES = crawl_result_of(_page("https://biz.example/", 200,
    '<html><body><div class="modal popup overlay dialog">Subscribe to our newsletter now</div></body></html>', depth=0))
# B: one page, two genuinely distinct interruption elements -> one affected page.
CR_E12_TWO_ELEMENTS_ONE_PAGE = crawl_result_of(_page("https://biz.example/", 200,
    '<html><body>'
    '<div class="modal">Sign up for our newsletter today</div>'
    '<div class="interstitial">Please subscribe to continue reading</div>'
    '</body></html>', depth=0))
# C: two separate pages each with an interruption -> two affected pages.
CR_E12_TWO_PAGES = crawl_result_of(
    _page("https://biz.example/", 200, '<html><body><div class="modal">Sign up for our newsletter today</div></body></html>', depth=0),
    _page("https://biz.example/about", 200, '<html><body><div class="modal">Join our newsletter for updates</div></body></html>'),
)
# D: no interruptions at all -> no finding.
CR_E12_NONE = crawl_result_of(_page("https://biz.example/", 200, "<html><body><p>Ordinary content.</p></body></html>", depth=0))

# --- E12: evidence readability (final hardening) ---
# H: nested text nodes must be joined with a space, not concatenated.
CR_E12_NESTED_TEXT_SPACING = crawl_result_of(_page("https://biz.example/", 200,
    '<html><body><div class="modal">\n  Please check your network\n  '
    '<span>connection</span>\n  <span>and try again.</span>\n</div></body></html>', depth=0))
# I: multiple nested elements across two distinct interruptions -> readability
# must hold for both, and detection (2 distinct elements -> 1 affected page)
# must be unaffected.
CR_E12_MULTI_NESTED = crawl_result_of(_page("https://biz.example/", 200,
    '<html><body>'
    '<div class="modal">Sign up for our <span>newsletter</span> today</div>'
    '<div class="interstitial">Please <span>subscribe</span> to continue reading</div>'
    '</body></html>', depth=0))

# --- E4: URL vs content alignment ---
CR_E4_MISMATCH = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                  _page("https://biz.example/product/analytics-suite", 200,
                                        "<html><head><title>Welcome</title></head><body><h1>Welcome to Our Company</h1></body></html>"))
CR_E4_MATCH = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                               _page("https://biz.example/product/analytics-suite", 200,
                                     "<html><head><title>Analytics</title></head><body><h1>Analytics Suite Overview</h1></body></html>"))

# --- E4: concatenated URL slugs (hardening regression) ---
CR_E4_CONCAT_HOWITWORKS = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                           _page("https://biz.example/howexampleworks", 200,
                                                 "<html><head><title>How Example Works</title></head><body><h1>How Example Works</h1></body></html>"))
CR_E4_CONCAT_ABOUTUS = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                        _page("https://biz.example/aboutus", 200,
                                              "<html><head><title>About Us</title></head><body><h1>About Us</h1></body></html>"))
CR_E4_CONCAT_CONTACTUS = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                          _page("https://biz.example/contactus", 200,
                                                "<html><head><title>Contact Us</title></head><body><h1>Contact Us</h1></body></html>"))
CR_E4_CONCAT_GENUINE_MISMATCH = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                                 _page("https://biz.example/pricing", 200,
                                                       "<html><head><title>Company History</title></head><body><h1>Company History</h1></body></html>"))

# --- E5: findability / click depth ---
_HOME_LINKS_DIRECT = '<a href="/contact">Contact</a>'
_HOME_LINKS_INDIRECT = '<a href="/section-a">Section A</a>'
CR_E5_DEEP = crawl_result_of(
    _page("https://biz.example/", 200, f"<html><body>{_HOME_LINKS_INDIRECT}</body></html>", depth=0),
    _page("https://biz.example/section-a", 200, '<html><body><a href="/section-a/b">B</a></body></html>', depth=1),
    _page("https://biz.example/section-a/b", 200, '<html><body><a href="/contact">Contact</a></body></html>', depth=2),
    _page("https://biz.example/contact", 200, "<html><body><h1>Contact Us</h1></body></html>", depth=3),
)
CR_E5_SHALLOW = crawl_result_of(
    _page("https://biz.example/", 200, f"<html><body>{_HOME_LINKS_DIRECT}</body></html>", depth=0),
    _page("https://biz.example/contact", 200, "<html><body><h1>Contact Us</h1></body></html>", depth=1),
)

# --- E6: navigation clarity ---
CR_E6_SMALL_AMBIGUOUS = crawl_result_of(_page(
    "https://biz.example/", 200,
    '<html><body><nav><a href="/">Home</a><a href="/solutions">Solutions</a><a href="/contact">Contact</a></nav></body></html>',
    depth=0))
CR_E6_LARGE_CLEAR = crawl_result_of(_page(
    "https://biz.example/", 200,
    '<html><body><nav>' + "".join(f'<a href="/{w.lower()}">{w}</a>' for w in
        ["Home", "Products", "Pricing", "About", "Contact", "Blog", "Docs", "Resources"]) + '</nav></body></html>',
    depth=0))

# --- E7/E9: structure and dead ends ---
_LONG_TEXT = " ".join(["This is unstructured filler content about our offering."] * 12)
CR_E7_E9_NO_STRUCTURE = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                         _page("https://biz.example/product/widget", 200,
                                               f"<html><body><h1>Widget</h1><p>{_LONG_TEXT}</p></body></html>"))
CR_E7_WITH_SUBHEADING = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                         _page("https://biz.example/product/widget", 200,
                                               f"<html><body><h1>Widget</h1><h2>Features</h2><p>{_LONG_TEXT}</p></body></html>"))
CR_E9_WITH_LINK = crawl_result_of(_page("https://biz.example/", 200,
                                         '<html><body><header>BizCo <a href="/product/widget">Products</a></header></body></html>', depth=0),
                                   _page("https://biz.example/product/widget", 200,
                                         '<html><body><h1>Widget</h1><p>Short.</p><a href="/product/other">Other</a></body></html>'))
CR_E9_DEAD_END = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                  _page("https://biz.example/product/widget", 200,
                                        "<html><body><h1>Widget</h1><p>Short.</p></body></html>"))

# --- E10: broken CTA (reuse-from-crawl path, no network needed) ---
CR_E10_BROKEN = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/pricing", 200,
          '<html><body><h1>Pricing</h1><a class="btn" href="/signup">Sign Up</a></body></html>'),
    _page("https://biz.example/signup", 404, "<html><body>Not found</body></html>"),
)
CR_E10_OK = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/pricing", 200,
          '<html><body><h1>Pricing</h1><a class="btn" href="/signup">Sign Up</a></body></html>'),
    _page("https://biz.example/signup", 200, "<html><body>Sign up form</body></html>"),
)

# --- E13: trust signals ---
CR_E13_FEW_SIGNALS = crawl_result_of(_page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
                                      _page("https://biz.example/product/widget", 200,
                                            "<html><body><h1>Widget</h1><p>Buy now.</p></body></html>"))
CR_E13_GOOD_SIGNALS = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/product/widget", 200, "<html><body><h1>Widget</h1><p>Buy now.</p></body></html>"),
    _page("https://biz.example/contact", 200, "<html><body>Contact us: contact@biz.example, phone.</body></html>"),
    _page("https://biz.example/about", 200, "<html><body>About us: our story and mission.</body></html>"),
    _page("https://biz.example/privacy", 200, "<html><body>Privacy Policy and Terms of Service.</body></html>"),
)
CR_E13_NONCOMMERCIAL = crawl_result_of(_page("https://docs.example/", 200, "<html><body><header>Docs</header></body></html>", depth=0),
                                        _page("https://docs.example/docs/guide", 200,
                                              "<html><body><h1>Guide</h1><p>Read the docs.</p></body></html>"))

# --- Proactive P5: breadcrumb opportunity ---
_P5_LONG_TEXT = " ".join(["This page has substantial real content about the topic."] * 8)
CR_P5_DEEP_NO_BREADCRUMB = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/products/widgets/pro", 200,
          f"<html><body><h1>Widget Pro</h1><p>{_P5_LONG_TEXT}</p></body></html>", depth=2),
)
CR_P5_DEEP_WITH_BREADCRUMB = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/products/widgets/pro", 200,
          f'<html><body><nav aria-label="breadcrumb">Home &gt; Products &gt; Widgets</nav>'
          f'<h1>Widget Pro</h1><p>{_P5_LONG_TEXT}</p></body></html>', depth=2),
)
CR_P5_SHALLOW_NO_BREADCRUMB = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/pricing", 200,
          f"<html><body><h1>Pricing</h1><p>{_P5_LONG_TEXT}</p></body></html>", depth=1),
)
CR_P5_JS_HEAVY_NO_BREADCRUMB = crawl_result_of(
    _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
    _page("https://biz.example/products/widgets/pro", 200,
          "<html><body><p>Short raw HTML, real content is JS-rendered.</p></body></html>", depth=2),
)
P5_JS_HEAVY_RENDER_COMPARISONS = [{
    "url": "https://biz.example/products/widgets/pro",
    "raw_text_length": 30, "rendered_text_length": 2000,
    "content_difference_ratio": 0.98, "significant_gap": True,
}]


def run_fixture_tests(mods):
    ar = mods["audit_runner"]
    results = []

    def check(label, condition, detail=""):
        results.append((label, condition))
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))

    def categories(findings):
        return {f["category"] for f in findings}

    print("\n" + "=" * 72)
    print("FIXTURE TESTS (local HTML, no network)")
    print("=" * 72)

    f = ar.run_engagement_audit(CR_E1_MISSING)
    check("E1 flagged when important page has no H1 and no org identity", "E1" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E1_GOOD)
    check("E1 NOT flagged when H1 + org identity present", "E1" not in categories(f), str(f))

    # --- Stage 7 regression: raw/rendered evidence handling ---
    # A page whose raw HTML is known (via render_comparisons) to be
    # substantially JS-rendered must not be flagged for "missing" content
    # that raw HTML simply can't show — confirmed false positive on a real
    # unseen site (E1/E2/E4/E7/E9 all share this risk; E1 tested here as
    # the representative, directly-confirmed case). Homepage here has real
    # identity content so E1 can only be about the product page.
    CR_E1_JS_OR_ERROR_BASE = crawl_result_of(
        _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
        _page("https://biz.example/product/widget", 200, "<html><body><p>Some text with no heading at all here.</p></body></html>"),
    )
    f = ar.run_engagement_audit(CR_E1_JS_OR_ERROR_BASE)
    check("(sanity) E1 flagged on the product page before any gating is applied",
          "E1" in categories(f), str(f))

    js_heavy_render_comparisons = [{
        "url": "https://biz.example/product/widget",
        "raw_text_length": 30, "rendered_text_length": 2000,
        "content_difference_ratio": 0.98, "significant_gap": True,
    }]
    f = ar.run_engagement_audit(CR_E1_JS_OR_ERROR_BASE, render_comparisons=js_heavy_render_comparisons)
    check("E1 NOT flagged when the page is known JS-heavy (significant_gap=True)",
          "E1" not in categories(f), str(f))

    # Same underlying HTML, but this time flagged via HTTP status instead of
    # JS-rendering (e.g. a bot-block/error page) -- also confirmed on a real
    # unseen site (several detectors evaluated 403/404 pages as if they were
    # real content).
    CR_E1_MISSING_403 = crawl_result_of(
        _page("https://biz.example/", 200, "<html><body><header>BizCo</header></body></html>", depth=0),
        _page("https://biz.example/product/widget", 403, "<html><body><p>Some text with no heading at all here.</p></body></html>"),
    )
    f = ar.run_engagement_audit(CR_E1_MISSING_403)
    check("E1 NOT flagged when the page returned an HTTP error status (403)",
          "E1" not in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E2_NO_CTA)
    check("E2 flagged when pricing page has zero CTAs", "E2" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E8_GENERIC_ONLY)
    check("E8 flagged when product page has only a generic CTA", "E8" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_GOOD_CTA)
    check("E2/E8 NOT flagged when a specific CTA is present", not ({"E2", "E8"} & categories(f)), str(f))

    f = ar.run_engagement_audit(CR_E4_MISMATCH)
    check("E4 flagged when URL implies a topic absent from H1/title", "E4" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E4_MATCH)
    check("E4 NOT flagged when H1 reflects the URL's implied topic", "E4" not in categories(f), str(f))

    # --- E4: concatenated (no-delimiter) URL slugs ---
    f = ar.run_engagement_audit(CR_E4_CONCAT_HOWITWORKS)
    check("E4 NOT flagged for concatenated slug '/howexampleworks/' matching 'How Example Works'",
          "E4" not in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E4_CONCAT_ABOUTUS)
    check("E4 NOT flagged for concatenated slug '/aboutus/' matching 'About Us'",
          "E4" not in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E4_CONCAT_CONTACTUS)
    check("E4 NOT flagged for concatenated slug '/contactus/' matching 'Contact Us'",
          "E4" not in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E4_CONCAT_GENUINE_MISMATCH)
    check("E4 STILL flagged for '/pricing/' with unrelated title 'Company History'",
          "E4" in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E5_DEEP)
    check("E5 flagged when contact page is 3 hops from homepage", "E5" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E5_SHALLOW)
    check("E5 NOT flagged when contact page is 1 hop from homepage", "E5" not in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E6_SMALL_AMBIGUOUS)
    check("E6 flagged for ambiguous label in a small (<=6 link) nav menu", "E6" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E6_LARGE_CLEAR)
    check("E6 NOT flagged for a large nav menu (>6 links) despite one loose label", "E6" not in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E7_E9_NO_STRUCTURE)
    check("E7 flagged for long unstructured content with no CTA/links", "E7" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E7_WITH_SUBHEADING)
    check("E7 NOT flagged once a sub-heading is present", "E7" not in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E7_E9_NO_STRUCTURE)
    check("E9 flagged for a page with zero CTAs and zero continuation links", "E9" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E9_WITH_LINK)
    check("E9 NOT flagged once a continuation link exists", "E9" not in categories(f), str(f))

    f = ar.run_engagement_audit(CR_E10_BROKEN)
    check("E10 flagged when a CTA's destination (already crawled) returned 404", "E10" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E10_OK)
    check("E10 NOT flagged when the CTA destination returned 200", "E10" not in categories(f), str(f))

    def _e12_finding(findings):
        return next((x for x in findings if x["category"] == "E12"), None)

    # A: one element matching 4 keywords at once -> counted as 1 affected page.
    f = ar.run_engagement_audit(CR_E12_OVERLAPPING_CLASSES)
    e12 = _e12_finding(f)
    check("E12 (A) one element matching 4 keywords -> exactly 1 affected page, not 4",
          e12 is not None and e12["title"].startswith("1 page(s)"), str(f))

    # B: one page, two distinct interruption elements -> still 1 affected page.
    f = ar.run_engagement_audit(CR_E12_TWO_ELEMENTS_ONE_PAGE)
    e12 = _e12_finding(f)
    check("E12 (B) two distinct elements on one page -> exactly 1 affected page",
          e12 is not None and e12["title"].startswith("1 page(s)"), str(f))

    # C: two separate pages each with an interruption -> 2 affected pages.
    f = ar.run_engagement_audit(CR_E12_TWO_PAGES)
    e12 = _e12_finding(f)
    check("E12 (C) two separate pages with interruptions -> exactly 2 affected pages",
          e12 is not None and e12["title"].startswith("2 page(s)"), str(f))

    # D: no interruptions at all -> no E12 finding.
    f = ar.run_engagement_audit(CR_E12_NONE)
    check("E12 (D) no interruptions present -> no finding", _e12_finding(f) is None, str(f))

    f = ar.run_engagement_audit(CR_E13_FEW_SIGNALS)
    check("E13 flagged for a commercial site with almost no trust signals", "E13" in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E13_GOOD_SIGNALS)
    check("E13 NOT flagged once contact/about/policy signals are present", "E13" not in categories(f), str(f))
    f = ar.run_engagement_audit(CR_E13_NONCOMMERCIAL)
    check("E13 NOT flagged on a non-commercial (docs-only) site at all", "E13" not in categories(f), str(f))

    # --- E11: real (local, no-network) browser viewport checks via file:// URLs ---
    vc = mods["viewport_check"]
    if vc.is_playwright_available():
        overflow_html = """
        <html><body style="margin:0">
          <div style="width:2000px;height:50px;background:#eee;">very wide content</div>
        </body></html>
        """
        nav_hide_html = """
        <html><head><style>
          @media (max-width: 500px) { nav { display: none; } }
        </style></head>
        <body><nav style="height:40px;background:#ccc;">Main Nav</nav><p>Content</p></body></html>
        """
        normal_html = """
        <html><body><nav style="height:40px;">Main Nav</nav><p>Simple responsive content.</p></body></html>
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="ea_viewport_fixtures_"))
        try:
            overflow_path = tmp_dir / "overflow.html"
            overflow_path.write_text(overflow_html, encoding="utf-8")
            nav_hide_path = tmp_dir / "nav_hide.html"
            nav_hide_path.write_text(nav_hide_html, encoding="utf-8")
            normal_path = tmp_dir / "normal.html"
            normal_path.write_text(normal_html, encoding="utf-8")

            vp = vc.check_viewport(overflow_path.as_uri())
            check("E11 detects horizontal overflow at mobile width (local file, real browser)",
                  any(i["type"] == "horizontal_overflow" for i in vp.get("mobile", {}).get("issues", [])), str(vp))

            vp2 = vc.check_viewport(nav_hide_path.as_uri())
            diff = vc.compare_viewports(vp2.get("desktop", {}), vp2.get("mobile", {}))
            check("E11 detects nav disappearing on mobile via compare_viewports (local file, real browser)",
                  any(i["type"] == "nav_disappears_on_mobile" for i in diff), str((vp2, diff)))

            vp3 = vc.check_viewport(normal_path.as_uri())
            diff3 = vc.compare_viewports(vp3.get("desktop", {}), vp3.get("mobile", {}))
            check("E11 NOT flagged for a normal responsive page (local file, real browser)",
                  not vp3.get("mobile", {}).get("issues", []) and not diff3, str((vp3, diff3)))
        finally:
            for p in tmp_dir.glob("*.html"):
                p.unlink(missing_ok=True)
            tmp_dir.rmdir()
    else:
        print("  [SKIP] E11 viewport tests -- Playwright not available")

    # --- Proactive P5: breadcrumb opportunity ---
    opp = ar.identify_proactive_opportunities(CR_P5_DEEP_NO_BREADCRUMB)
    check("P5 fires: deep page with substantial content and no breadcrumb trail",
          any("breadcrumb" in o["title"].lower() for o in opp), str(opp))
    check("P5 entry has no 'severity' field (not a defect)",
          opp and "severity" not in opp[0], str(opp))

    opp = ar.identify_proactive_opportunities(CR_P5_DEEP_WITH_BREADCRUMB)
    check("P5 does NOT fire when a breadcrumb trail is already present", opp == [], str(opp))

    opp = ar.identify_proactive_opportunities(CR_P5_SHALLOW_NO_BREADCRUMB)
    check("P5 does NOT fire on a shallow (depth < 2) page", opp == [], str(opp))

    opp = ar.identify_proactive_opportunities(
        CR_P5_JS_HEAVY_NO_BREADCRUMB, render_comparisons=P5_JS_HEAVY_RENDER_COMPARISONS)
    check("P5 does NOT fire on a JS-heavy page excluded via the unreliable-URL gate", opp == [], str(opp))

    n_pass = sum(1 for _, ok in results if ok)
    n_total = len(results)
    print(f"\nFIXTURE RESULTS: {n_pass}/{n_total} passed")
    return n_pass, n_total


_BOILERPLATE_ACTIONS = {
    "fix this issue.", "review and fix the problem.", "improve seo.",
    "update the page accordingly.", "investigate and resolve.", "ensure this is correct.",
}


def test_suggested_action_quality(mods):
    """Part 2 regression: every E1-E13 suggested_action is non-empty, not
    generic boilerplate, and mentions remediation content specific to that
    detector. Detection/severity/evidence logic is untouched by Part 2 --
    this only verifies the upgraded suggested_action TEXT. Reuses the same
    fixtures already proven to trigger each detector above.
    """
    print("\n" + "=" * 72 + "\nPART 2 -- SUGGESTED ACTION QUALITY (E1-E13)\n" + "=" * 72)
    ar = mods["audit_runner"]
    vc = mods["viewport_check"]
    all_ok = True
    by_category: dict[str, list[dict]] = {}

    def _collect(findings):
        for f in findings:
            by_category.setdefault(f.get("category"), []).append(f)

    _collect(ar.run_engagement_audit(CR_E1_MISSING))
    _collect(ar.run_engagement_audit(CR_E2_NO_CTA))
    _collect(ar.run_engagement_audit(CR_E8_GENERIC_ONLY))
    _collect(ar.run_engagement_audit(CR_E4_MISMATCH))
    _collect(ar.run_engagement_audit(CR_E5_DEEP))
    _collect(ar.run_engagement_audit(CR_E6_SMALL_AMBIGUOUS))
    _collect(ar.run_engagement_audit(CR_E7_E9_NO_STRUCTURE))
    _collect(ar.run_engagement_audit(CR_E10_BROKEN))
    _collect(ar.run_engagement_audit(CR_E12_TWO_ELEMENTS_ONE_PAGE))
    _collect(ar.run_engagement_audit(CR_E13_FEW_SIGNALS))

    if vc.is_playwright_available():
        overflow_html = """
        <html><body style="margin:0">
          <div style="width:2000px;height:50px;background:#eee;">very wide content</div>
        </body></html>
        """
        nav_hide_html = """
        <html><head><style>
          @media (max-width: 500px) { nav { display: none; } }
        </style></head>
        <body><nav style="height:40px;background:#ccc;">Main Nav</nav><p>Content</p></body></html>
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="ea_action_quality_fixtures_"))
        try:
            overflow_path = tmp_dir / "overflow.html"
            overflow_path.write_text(overflow_html, encoding="utf-8")
            nav_hide_path = tmp_dir / "nav_hide.html"
            nav_hide_path.write_text(nav_hide_html, encoding="utf-8")

            for path, homepage_url in ((overflow_path, overflow_path.as_uri()), (nav_hide_path, nav_hide_path.as_uri())):
                cr = crawl_result_of(_page(homepage_url, 200, path.read_text(encoding="utf-8"), depth=0))
                _collect(ar.run_engagement_audit(cr, max_viewport_pages=1))
        finally:
            for p in tmp_dir.glob("*.html"):
                p.unlink(missing_ok=True)
            tmp_dir.rmdir()
    else:
        print("  [SKIP] E11 -- Playwright not available, skipping E11 action-quality check")

    _EXPECTED_KEYWORDS = {
        "E1": ["h1"],
        "E2": ["cta"],
        "E8": ["generic"],
        "E4": ["url segment"],
        "E5": ["clicks"],
        "E6": ["navigation labels"],
        "E7": ["sub-headings"],
        "E9": ["next step"],
        "E10": ["http 200"],
        "E12": ["modal"],
        "E13": ["trust signal"],
    }
    if vc.is_playwright_available():
        _EXPECTED_KEYWORDS["E11"] = ["mobile"]

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


def test_e12_evidence_readability(mods):
    """Final hardening regression: E12 evidence text must join nested DOM
    text nodes with a space (Fix 3), and this must not change interruption
    detection semantics (firing behavior, affected-page counting).
    """
    print("\n" + "=" * 72 + "\nE12 EVIDENCE READABILITY (final hardening)\n" + "=" * 72)
    ar = mods["audit_runner"]
    all_ok = True

    def _check(label, condition, detail=""):
        nonlocal all_ok
        all_ok = all_ok and condition
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if not condition and detail:
            print(f"    {detail}")

    def _e12_finding(findings):
        return next((x for x in findings if x["category"] == "E12"), None)

    # H: nested text nodes joined with a space, not concatenated.
    f = ar.run_engagement_audit(CR_E12_NESTED_TEXT_SPACING)
    e12 = _e12_finding(f)
    evidence = (e12 or {}).get("evidence", "")
    _check("Case H: nested text nodes are joined with readable spacing",
           "network connection and try again" in evidence, evidence)
    _check("Case H: nested text nodes are NOT concatenated without spaces",
           "networkconnection" not in evidence.lower() and "againjoin" not in evidence.lower(), evidence)

    # I: multiple nested elements -> both readable, detection semantics unaffected
    # (2 distinct interruption elements on one page -> exactly 1 affected page).
    f = ar.run_engagement_audit(CR_E12_MULTI_NESTED)
    e12 = _e12_finding(f)
    evidence = (e12 or {}).get("evidence", "")
    _check("Case I: readable extraction holds across multiple nested elements",
           "our newsletter today" in evidence and "please subscribe" in evidence.lower(), evidence)
    _check("Case I: detection semantics unaffected -- still exactly 1 affected page",
           e12 is not None and e12["title"].startswith("1 page(s)"), str(f))

    # J: existing detection behavior (firing + affected-page counts) is unchanged
    # by the readability-only fix.
    f = ar.run_engagement_audit(CR_E12_OVERLAPPING_CLASSES)
    e12 = _e12_finding(f)
    _check("Case J: (A) one element matching 4 keywords -> still exactly 1 affected page",
           e12 is not None and e12["title"].startswith("1 page(s)"), str(f))

    f = ar.run_engagement_audit(CR_E12_TWO_PAGES)
    e12 = _e12_finding(f)
    _check("Case J: (C) two separate pages with interruptions -> still exactly 2 affected pages",
           e12 is not None and e12["title"].startswith("2 page(s)"), str(f))

    f = ar.run_engagement_audit(CR_E12_NONE)
    _check("Case J: (D) no interruptions present -> still no finding", _e12_finding(f) is None, str(f))

    return all_ok


def run_live_smoke_test(mods, site_url="https://example.com/", max_pages=3):
    print("\n" + "=" * 72)
    print("LIVE SMOKE TEST (single small real site)")
    print(f"Site: {site_url}  max_pages: {max_pages}")
    print("=" * 72)

    t0 = time.time()
    robots_data = mods["robots_check"].fetch_robots_txt(site_url, timeout=10)
    is_allowed = None
    if robots_data.get("parser"):
        p = robots_data["parser"]
        is_allowed = lambda url: p.can_fetch("BrandAIReadinessAudit", url)

    crawl_result = mods["crawl"].bounded_crawl(site_url, is_allowed=is_allowed, max_pages=max_pages, max_depth=1, timeout=12)
    pages = crawl_result.get("pages", [])
    print(f"  pages fetched: {len(pages)}")

    try:
        findings = mods["audit_runner"].run_engagement_audit(crawl_result)
        crashed = False
    except Exception:
        import traceback
        traceback.print_exc()
        findings = []
        crashed = True

    duration = round(time.time() - t0, 1)
    print(f"  duration: {duration}s")
    print(f"  findings: {len(findings)}")
    for finding in findings:
        print(f"    [{finding['severity'].upper()}] {finding['category']}: {finding['title']}")
        print(f"      Evidence: {finding['evidence'][:200]}")

    print(f"\n  PIPELINE CRASH: {'YES (BAD)' if crashed else 'no'}")
    return not crashed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--site", default="https://example.com/")
    args = parser.parse_args()

    print("=" * 72)
    print("Brand AI Readiness -- engagement-audit Validation (Stage 4)")
    print(f"Python: {sys.version.split()[0]}  |  CWD: {os.getcwd()}")
    print("=" * 72)

    mods = load_all_modules()

    n_pass, n_total = run_fixture_tests(mods)

    action_quality_ok = test_suggested_action_quality(mods)
    if not action_quality_ok:
        print("\nPart 2 suggested_action quality test FAILED")

    e12_readability_ok = test_e12_evidence_readability(mods)
    if not e12_readability_ok:
        print("\nE12 evidence readability regression test FAILED")

    live_ok = True
    if not args.skip_live:
        live_ok = run_live_smoke_test(mods, site_url=args.site)

    print("\n" + "=" * 72)
    print("OVERALL RESULT")
    print("=" * 72)
    print(f"Fixture tests: {n_pass}/{n_total} passed")
    print(f"Live smoke test: {'OK' if live_ok else 'CRASHED'}")

    if n_pass != n_total or not live_ok or not action_quality_ok or not e12_readability_ok:
        sys.exit(1)
