#!/usr/bin/env python3
r"""
Stage 3 Validation Test Runner -- Freshness & Corroboration

Two kinds of checks, per the Stage 3 sign-off requirements:
  1. Deterministic fixture tests against LOCAL, CONTROLLED HTML (no network) —
     these are the ground truth for whether each detector actually behaves
     correctly, since no live site can be relied on to have a stable,
     guaranteed contradiction.
  2. One small real-site smoke test (https://example.com by default) to prove
     the pipeline runs end-to-end against real crawl data with no crash and
     no false positives on ordinary content.

Run with the project .venv:
    .venv\Scripts\python.exe validate_freshness_audit.py [--skip-live]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time

logging_configured = False
import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(__file__)
FC_BASE = os.path.join(ROOT, "brand-ai-readiness-audit", "skills", "freshness-corroboration", "scripts")
CR_BASE = os.path.join(ROOT, "brand-ai-readiness-audit", "skills", "crawl-render-audit", "scripts")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_all_modules():
    mods = {}
    for name in ["identity_analysis", "freshness_analysis", "fact_consistency", "corroboration"]:
        mods[name] = load_module(os.path.join(FC_BASE, f"{name}.py"), name)

    ar_path = os.path.join(FC_BASE, "audit_runner.py")
    with open(ar_path, encoding="utf-8") as f:
        src = f.read()
    for m in ["identity_analysis", "freshness_analysis", "fact_consistency", "corroboration"]:
        src = src.replace(f"from .{m} import", f"from {m} import")
    tmp = os.path.join(FC_BASE, "_fc_ar_tmp.py")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        mods["audit_runner"] = load_module(tmp, "freshness_audit_runner")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # Reused from crawl-render-audit for the live smoke test only.
    mods["crawl"] = load_module(os.path.join(CR_BASE, "crawl.py"), "cr_crawl")
    mods["robots_check"] = load_module(os.path.join(CR_BASE, "robots_check.py"), "cr_robots_check")
    return mods


# ---------------------------------------------------------------------------
# Local HTML fixtures
# ---------------------------------------------------------------------------

def _page(url, status, body, depth=1):
    return {"url": url, "final_url": url, "status": status, "body": body,
            "headers": {}, "redirects": [], "response_time_ms": 10, "error": None, "depth": depth}


FIXTURE_IDENTITY_CONTRADICTION = [
    _page("https://acme.example/", 200, """
    <html><head><title>Acme Corp - Home</title>
    <script type="application/ld+json">{"@type":"Organization","name":"Acme Corp"}</script>
    </head><body><h1>Acme Corp</h1></body></html>
    """, depth=0),
    _page("https://acme.example/contact", 200, """
    <html><head><title>Contact</title>
    <script type="application/ld+json">{"@type":"Organization","name":"Beta Industries"}</script>
    </head><body><h1>Contact Us</h1></body></html>
    """),
]

FIXTURE_LEGIT_BRAND_VARIATION = [
    _page("https://widgetco.example/", 200, """
    <html><head><title>WidgetCo - Home</title>
    <meta property="og:site_name" content="WidgetCo">
    <script type="application/ld+json">{"@type":"Organization","name":"WidgetCo","legalName":"Widget Company Holdings, LLC"}</script>
    </head><body><h1>WidgetCo</h1></body></html>
    """, depth=0),
    _page("https://widgetco.example/about", 200, """
    <html><head><title>About WidgetCo, Inc.</title>
    <script type="application/ld+json">{"@type":"Organization","name":"WidgetCo, Inc."}</script>
    </head><body><h1>About WidgetCo, Inc.</h1></body></html>
    """),
]

# Reproduces the exact false-positive pattern confirmed on a real unseen
# site in Stage 7: a homepage whose H1 is a generic UI/personalization
# label (not a brand name), plus ordinary category pages each with their
# own topic as H1 — none of this is a genuine identity contradiction.
FIXTURE_ORDINARY_MULTIPAGE_SITE = [
    _page("https://shop.example/", 200, """
    <html><body><h1>For You</h1></body></html>
    """, depth=0),
    _page("https://shop.example/fashion", 200, """
    <html><body><h1>Fashion</h1></body></html>
    """),
    _page("https://shop.example/mobiles", 200, """
    <html><body><h1>Mobiles</h1></body></html>
    """),
]

# --- Hardening regression: og:site_name section/sub-property identity ---
# Scenario A: a section page declares its OWN og:site_name that is clearly
# related to (shares a token with) the homepage's declared organization,
# but is not textually identical -- must NOT be flagged as a contradiction.
FIXTURE_SECTION_SPECIFIC_IDENTITY = [
    _page("https://acme.example/", 200, """
    <html><head><title>Acme</title>
    <script type="application/ld+json">{"@type":"Organization","name":"Acme Corporation"}</script>
    </head><body><h1>Acme</h1></body></html>
    """, depth=0),
    _page("https://acme.example/developers", 200, """
    <html><head><meta property="og:site_name" content="Acme Developers"></head>
    <body><h1>Developer Portal</h1></body></html>
    """),
    _page("https://acme.example/blog", 200, """
    <html><head><meta property="og:site_name" content="How Acme Works"></head>
    <body><h1>Blog</h1></body></html>
    """),
]

# Scenario B: an identity-bearing page declares an Organization schema name
# that shares NO token with the homepage's -- a genuine contradiction and
# must still be detected.
FIXTURE_GENUINE_CROSS_SECTION_CONTRADICTION = [
    _page("https://acme.example/", 200, """
    <html><head><script type="application/ld+json">{"@type":"Organization","name":"Acme Corporation"}</script>
    </head><body><h1>Acme</h1></body></html>
    """, depth=0),
    _page("https://acme.example/about", 200, """
    <html><head><script type="application/ld+json">{"@type":"Organization","name":"Completely Different Corporation"}</script>
    </head><body><h1>About</h1></body></html>
    """),
]

# Scenario: a homepage's H1 is a value-proposition tagline (not a name),
# repeated consistently as og:site_name on other pages -- must NOT be
# flagged as a contradiction (confirmed false positive on a real unseen site).
FIXTURE_TAGLINE_HOMEPAGE_H1 = [
    _page("https://acme.example/", 200, """
    <html><head><meta property="og:site_name" content="Acme Health"></head>
    <body><h1>The operating system for D2C example brands.</h1></body></html>
    """, depth=0),
    _page("https://acme.example/pricing", 200, """
    <html><head><meta property="og:site_name" content="Acme Health"></head>
    <body><h1>Pricing</h1></body></html>
    """),
    _page("https://acme.example/blog/some-article", 200, """
    <html><head><meta property="og:site_name" content="Acme Health"></head>
    <body><h1>Some Article</h1></body></html>
    """),
]

FIXTURE_AMBIGUOUS_ENTITY_HTML = """
<html><head><title>Atlas</title>
<script type="application/ld+json">{"@type":"Organization","name":"Atlas"}</script>
</head><body><h1>Atlas</h1></body></html>
"""

FIXTURE_H1_ONLY_NO_DECLARATION_HTML = """
<html><head><title>Example Domain</title></head>
<body><h1>Example Domain</h1><p>This domain is for illustrative examples.</p></body></html>
"""

FIXTURE_WELL_SPECIFIED_ENTITY_HTML = """
<html><head><title>Riverside Family Dental Clinic</title>
<script type="application/ld+json">{
  "@type":"LocalBusiness","name":"Riverside Family Dental Clinic",
  "description":"A family-owned dental clinic serving the Riverside community since 1998.",
  "address":{"streetAddress":"12 Elm St","addressLocality":"Riverside","addressCountry":"US"},
  "logo":"https://riversidedental.example/logo.png",
  "sameAs":["https://www.linkedin.com/company/riverside-dental"]
}</script>
</head><body><h1>Riverside Family Dental Clinic</h1></body></html>
"""

FIXTURE_CONTACT_MISMATCH = [
    _page("https://smallco.example/", 200, """
    <html><body><footer>Call us: (555) 123-4567</footer></body></html>
    """),
    _page("https://smallco.example/contact", 200, """
    <html><body><footer>Call us: (555) 999-0000</footer></body></html>
    """),
]

FIXTURE_SAME_PAGE_MULTIPLE_PHONES = [
    _page("https://biz.example/contact", 200, """
    <html><body><footer>Telephone: 044-45614709 / 044-45714709</footer></body></html>
    """),
]

FIXTURE_SAME_PRODUCT_PRICE_CONTRADICTION = [
    _page("https://shop.example/widget", 200, """
    <html><body><h1>Widget Pro</h1><p>Price: $49.99</p></body></html>
    """),
    _page("https://shop.example/deals/widget", 200, """
    <html><body><h1>Widget Pro</h1><p>Special price: $39.99</p></body></html>
    """),
]

FIXTURE_DIFFERENT_PRODUCT_PRICES = [
    _page("https://shop.example/widget", 200, """
    <html><body><h1>Widget Pro</h1><p>Price: $49.99</p></body></html>
    """),
    _page("https://shop.example/gadget", 200, """
    <html><body><h1>Gadget Max</h1><p>Price: $199.99</p></body></html>
    """),
]

FIXTURE_STALE_OFFER_HTML = """
<html><body>
<p>Join us in 2019 for our annual conference!</p>
<p>Offer valid until January 1, 2020.</p>
</body></html>
"""

FIXTURE_EVERGREEN_HTML = """
<html><body>
<p>Founded in 1998, our mission has always been to serve the community.</p>
<p>Copyright 2015 Acme Foundation.</p>
</body></html>
"""

# --- Proactive P3: sameAs corroboration opportunity fixtures ---

# Well-specified (3+ word) org name, no sameAs at all -> low ambiguity risk,
# so this is a genuine opportunity, not something F2 already flags.
FIXTURE_P3_SAMEAS_OPPORTUNITY = [
    _page("https://riversidedental.example/", 200, """
    <html><head><title>Riverside Family Dental Clinic</title>
    <script type="application/ld+json">{
      "@type":"LocalBusiness","name":"Riverside Family Dental Clinic",
      "description":"A family-owned dental clinic serving the Riverside community since 1998.",
      "address":{"streetAddress":"12 Elm St","addressLocality":"Riverside","addressCountry":"US"},
      "logo":"https://riversidedental.example/logo.png"
    }</script>
    </head><body><h1>Riverside Family Dental Clinic</h1></body></html>
    """, depth=0),
]

# Generic single-word name, no sameAs -> F2 already flags this as an
# ambiguity risk; P3 must NOT pile on with a redundant, overlapping suggestion.
FIXTURE_P3_AMBIGUOUS_NO_FIRE = [
    _page("https://atlas.example/", 200, """
    <html><head><script type="application/ld+json">{"@type":"Organization","name":"Atlas"}</script>
    </head><body><h1>Atlas</h1></body></html>
    """, depth=0),
]

# Already has sameAs -> the opportunity doesn't exist; must NOT fire.
FIXTURE_P3_HAS_SAMEAS = [
    _page("https://riversidedental.example/", 200, FIXTURE_WELL_SPECIFIED_ENTITY_HTML, depth=0),
]

# --- Proactive P4: freshness metadata opportunity fixtures ---

# >=2 distinct high-sensitivity categories, no staleness signals, no
# datePublished/dateModified anywhere -> genuine opportunity.
FIXTURE_P4_OPPORTUNITY = [
    _page("https://biz.example/updates", 200, """
    <html><body><p>Check our latest price update and register for our upcoming event.</p></body></html>
    """),
]

# Only a single high-sensitivity category -> not "genuinely identifiable"
# time-sensitive content; must NOT fire.
FIXTURE_P4_SINGLE_CATEGORY = [
    _page("https://biz.example/pricing-note", 200, """
    <html><body><p>Check our latest price.</p></body></html>
    """),
]

# Multiple high-sensitivity categories AND actual staleness evidence already
# present -> this is F4's territory, not P4's; must NOT fire (no overlap).
FIXTURE_P4_HAS_STALENESS = [
    _page("https://event.example/conf", 200, """
    <html><body>
    <p>Join us in 2019 for our annual conference!</p>
    <p>Offer valid until January 1, 2020. Grab this sale now.</p>
    </body></html>
    """),
]

# Multiple high-sensitivity categories but a dateModified is already present
# -> the opportunity doesn't exist; must NOT fire.
FIXTURE_P4_HAS_DATEMODIFIED = [
    _page("https://biz.example/promo", 200, """
    <html><head><script type="application/ld+json">{"@type":"Article","dateModified":"2026-01-01"}</script>
    </head><body><p>Check our latest price update and register for our upcoming event.</p></body></html>
    """),
]


def run_fixture_tests(mods):
    ia = mods["identity_analysis"]
    fa = mods["freshness_analysis"]
    fc = mods["fact_consistency"]
    co = mods["corroboration"]
    ar = mods["audit_runner"]

    results = []

    def check(label, condition, detail=""):
        results.append((label, condition, detail))
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))

    print("\n" + "=" * 72)
    print("FIXTURE TESTS (local HTML, no network)")
    print("=" * 72)

    def _identity_signals(pages):
        sigs = []
        for p in pages:
            sig = ia.extract_identity_signals(p["body"], p["url"])
            sig["depth"] = p.get("depth", 1)
            sigs.append(sig)
        return sigs

    # --- F1: identity contradiction ---
    signals = _identity_signals(FIXTURE_IDENTITY_CONTRADICTION)
    cmp1 = ia.compare_identity(signals)
    check("F1 identity contradiction detected (Acme Corp vs Beta Industries)",
          not cmp1["consistent"] and len(cmp1["contradictions"]) > 0,
          str(cmp1))

    # --- F1: legitimate brand/legal-name variation NOT flagged ---
    signals2 = _identity_signals(FIXTURE_LEGIT_BRAND_VARIATION)
    cmp2 = ia.compare_identity(signals2)
    check("F1 legit brand/legal-name variation NOT flagged (WidgetCo / legalName)",
          cmp2["consistent"], str(cmp2))

    # --- F1: section-specific og:site_name NOT flagged (hardening regression) ---
    # Scenario A: different pages declare their own og:site_name, sharing a
    # token with the homepage's org name but not textually identical.
    signals_section = _identity_signals(FIXTURE_SECTION_SPECIFIC_IDENTITY)
    cmp_section = ia.compare_identity(signals_section)
    check("F1 section-specific og:site_name (shares a token with homepage org) NOT flagged",
          cmp_section["consistent"], str(cmp_section))

    # Scenario B: a genuine cross-page contradiction (no shared token at all)
    # must still be detected.
    signals_genuine = _identity_signals(FIXTURE_GENUINE_CROSS_SECTION_CONTRADICTION)
    cmp_genuine = ia.compare_identity(signals_genuine)
    check("F1 genuine cross-page contradiction (no shared token) still detected",
          not cmp_genuine["consistent"] and len(cmp_genuine["contradictions"]) > 0, str(cmp_genuine))

    # --- F1: tagline homepage H1 NOT treated as a name (final hardening) ---
    signals_tagline = _identity_signals(FIXTURE_TAGLINE_HOMEPAGE_H1)
    cmp_tagline = ia.compare_identity(signals_tagline)
    check("F1 tagline-style homepage H1 NOT compared as if it were the brand name",
          cmp_tagline["consistent"], str(cmp_tagline))

    # --- F1: ordinary multi-page site NOT flagged (Stage 7 regression) ---
    # Reproduces the confirmed real-world false positive: homepage H1 is a
    # generic label ("For You"), other pages' H1s are just their own topic
    # ("Fashion", "Mobiles") — none of this is a brand identity contradiction.
    signals3 = _identity_signals(FIXTURE_ORDINARY_MULTIPAGE_SITE)
    cmp3 = ia.compare_identity(signals3)
    check("F1 ordinary multi-page site (generic homepage label + category pages) NOT flagged",
          cmp3["consistent"], str(cmp3))

    # --- F2: entity ambiguity risk (generic single-word name, no signals) ---
    amb_signals = [ia.extract_identity_signals(FIXTURE_AMBIGUOUS_ENTITY_HTML, "https://atlas.example/")]
    amb_profile = ia.build_site_identity_profile(amb_signals)
    amb_assessment = ia.assess_entity_ambiguity(amb_profile)
    check("F2 ambiguity risk flagged for generic single-word name with no distinguishing signals",
          amb_assessment["risk_level"] in ("medium", "high"), str(amb_assessment))

    # --- F2: well-specified entity NOT flagged ---
    ws_signals = [ia.extract_identity_signals(FIXTURE_WELL_SPECIFIED_ENTITY_HTML, "https://riversidedental.example/")]
    ws_profile = ia.build_site_identity_profile(ws_signals)
    ws_assessment = ia.assess_entity_ambiguity(ws_profile)
    check("F2 well-specified multi-word entity with full signals NOT flagged (risk=low)",
          ws_assessment["risk_level"] == "low", str(ws_assessment))

    # --- F2: bare H1 with no schema/og:site_name is NOT treated as a reliable
    # identity declaration (must not penalize the many ordinary sites with no
    # Organization schema at all) ---
    h1only_signals = [ia.extract_identity_signals(FIXTURE_H1_ONLY_NO_DECLARATION_HTML, "https://example.com/")]
    h1only_profile = ia.build_site_identity_profile(h1only_signals)
    h1only_assessment = ia.assess_entity_ambiguity(h1only_profile)
    check("F2 bare H1 fallback (no schema/og:site_name) NOT flagged as ambiguity risk",
          h1only_assessment["risk_level"] == "unknown", str(h1only_assessment))

    def _facts(pages):
        return [fc.extract_facts(p["body"], p["url"], depth=p.get("depth", 1)) for p in pages]

    # --- F3: same-entity contact mismatch (different pages) ---
    facts_contact = _facts(FIXTURE_CONTACT_MISMATCH)
    contradictions_contact = fc.find_contradictions(facts_contact)
    check("F3 same-entity footer phone contradiction detected (different pages)",
          any(c["field"] == "phone" for c in contradictions_contact), str(contradictions_contact))

    # --- F3: same-page multiple phone numbers NOT flagged (Stage 7 regression) ---
    # Reproduces the confirmed bug: a single page's footer listing two
    # numbers together ("Call: 044-1234 / 044-5678") is not a contradiction.
    facts_same_page_multi = _facts(FIXTURE_SAME_PAGE_MULTIPLE_PHONES)
    contradictions_same_page_multi = fc.find_contradictions(facts_same_page_multi)
    check("F3 two phone numbers on the SAME page NOT flagged as a contradiction",
          not any(c["field"] == "phone" for c in contradictions_same_page_multi), str(contradictions_same_page_multi))

    # --- F3: founding-year extraction strength (hardening regression) ---
    strong_examples = [
        ("Founded in 2007", 2007),
        ("Established in 2007", 2007),
        ("The company was formed in 2007", 2007),
    ]
    for text, expected_year in strong_examples:
        facts = fc.extract_facts(f"<html><body><p>{text}.</p></body></html>", "https://biz.example/about", depth=1)
        found = next((d["value"] for d in facts["dates"] if d["type"] == "founded_year"), None)
        check(f"F3 founding-year extracted from '{text}'", found == expected_year, str(facts["dates"]))

    weak_examples = ["Effective since 2024", "Available since 2024"]
    for text in weak_examples:
        facts = fc.extract_facts(f"<html><body><p>{text}.</p></body></html>", "https://biz.example/policy", depth=1)
        found = [d for d in facts["dates"] if d["type"] == "founded_year"]
        check(f"F3 '{text}' NOT extracted as founding-year evidence", found == [], str(facts["dates"]))

    # Two genuine conflicting founding-year statements must still produce a finding.
    facts_founding_conflict = [
        fc.extract_facts("<html><body><p>Founded in 2007.</p></body></html>", "https://biz.example/about", depth=1),
        fc.extract_facts("<html><body><p>Established in 2015.</p></body></html>", "https://biz.example/history", depth=1),
    ]
    contradictions_founding = fc.find_contradictions(facts_founding_conflict)
    check("F3 genuine conflicting founding-year statements still detected",
          any(c["field"] == "founding_year" for c in contradictions_founding), str(contradictions_founding))

    # --- F3: same-product price contradiction ---
    facts_price_same = _facts(FIXTURE_SAME_PRODUCT_PRICE_CONTRADICTION)
    contradictions_price_same = fc.find_contradictions(facts_price_same)
    check("F3 same-product price contradiction detected (Widget Pro $49.99 vs $39.99)",
          any(c["field"] == "price" for c in contradictions_price_same), str(contradictions_price_same))

    # --- F3: different-product prices NOT flagged ---
    facts_price_diff = _facts(FIXTURE_DIFFERENT_PRODUCT_PRICES)
    contradictions_price_diff = fc.find_contradictions(facts_price_diff)
    check("F3 different-product prices NOT flagged (Widget Pro vs Gadget Max)",
          not any(c["field"] == "price" for c in contradictions_price_diff), str(contradictions_price_diff))

    # --- F3: homepage price NOT extracted as a "product" (Stage 7 regression) ---
    # Reproduces the confirmed bug: a homepage's generic H1 ("For You") plus
    # any price mentioned anywhere on the page must not become a fake
    # "product price" fact for comparison.
    homepage_facts = fc.extract_facts(
        '<html><body><h1>For You</h1><p>Featured deal: $69,999</p></body></html>',
        "https://shop.example/", depth=0,
    )
    check("F3 homepage H1 does NOT get a price/product entry",
          homepage_facts["prices"] == [], str(homepage_facts))

    # --- F4: stale time-sensitive content flagged ---
    fresh_stale = fa.analyze_freshness(FIXTURE_STALE_OFFER_HTML, "https://event.example/")
    check("F4 stale offer/event content flagged (past-tense year + expired offer)",
          len(fresh_stale["staleness_signals"]) > 0, str(fresh_stale["staleness_signals"]))

    # --- F4: old-but-evergreen content NOT flagged ---
    fresh_evergreen = fa.analyze_freshness(FIXTURE_EVERGREEN_HTML, "https://about.example/")
    check("F4 old-but-evergreen content NOT flagged (founding history, old copyright)",
          len(fresh_evergreen["staleness_signals"]) == 0, str(fresh_evergreen["staleness_signals"]))

    # --- F4: assess_staleness gating ---
    stale_assessment = fa.assess_staleness("offer", "2020-01-01")
    check("F4 assess_staleness flags an old high-sensitivity offer date",
          stale_assessment["potentially_stale"] is True, str(stale_assessment))
    evergreen_assessment = fa.assess_staleness("history", "1998-01-01")
    check("F4 assess_staleness does NOT flag old date for non-time-sensitive content type",
          stale_assessment["is_time_sensitive"] and not evergreen_assessment["is_time_sensitive"],
          str(evergreen_assessment))
    missing_date_assessment = fa.assess_staleness("offer", None)
    check("F4 assess_staleness does NOT flag staleness merely because date is missing",
          missing_date_assessment["potentially_stale"] is False, str(missing_date_assessment))

    # --- F5: broken sameAs reference ---
    broken_results = co.verify_same_as_links(
        ["https://this-domain-should-not-exist-brandaudit-test.invalid/org"],
        expected_name="Acme Corp", max_links=5, timeout=5.0,
    )
    check("F5 unreachable sameAs link correctly marked not reachable",
          len(broken_results) == 1 and broken_results[0]["reachable"] is False, str(broken_results))
    check("F5 a genuine connection failure is NOT marked likely_blocked (stays 'broken', not 'unverifiable')",
          broken_results[0].get("likely_blocked") is False, str(broken_results))

    # --- F5: blocked/unverifiable vs genuinely broken (Stage 7 regression) ---
    # Reproduces the confirmed issue: a 403 (bot-blocking) must classify as
    # "unverifiable", not "broken" — a broken link and a blocked-by-the-
    # platform link are different situations and must not be conflated.
    same_as_blocked = [{"url": "https://linkedin.example/company/acme", "reachable": False,
                         "status": 403, "known_platform": True, "name_found": None,
                         "likely_blocked": True, "error": None}]
    blocked_results = co.corroborate_claims([], same_as_results=same_as_blocked, external_sources=None)
    check("F5 a 403 (bot-blocking) sameAs response classifies as 'unverifiable', not 'broken'",
          any(r["status"] == "unverifiable" for r in blocked_results)
          and not any(r["status"] == "broken" for r in blocked_results),
          str(blocked_results))

    same_as_genuinely_broken = [{"url": "https://acme.example/dead-link", "reachable": False,
                                  "status": 404, "known_platform": False, "name_found": None,
                                  "likely_blocked": False, "error": None}]
    dead_results = co.corroborate_claims([], same_as_results=same_as_genuinely_broken, external_sources=None)
    check("F5 a genuine 404 sameAs response still classifies as 'broken'",
          any(r["status"] == "broken" for r in dead_results), str(dead_results))

    # A blocked reference must not count toward the confidence summary's
    # broken/unrelated bucket, and must not surface as a finding upstream.
    blocked_confidence = co.assess_corroboration_confidence(blocked_results)
    check("F5 'unverifiable' is tracked separately and NOT counted as broken/unrelated",
          blocked_confidence["unverifiable_references"] == 1 and blocked_confidence["broken_or_unrelated_references"] == 0,
          str(blocked_confidence))

    # --- F5: corroboration absence vs contradiction ---
    claims = [{"claim": "organization_identity", "value": "Acme Corp", "category": "identity"}]
    no_source_results = co.corroborate_claims(claims, same_as_results=[], external_sources=None)
    check("F5 absence of external sources yields 'not_attempted', not a finding",
          all(r["status"] != "contradicted" for r in no_source_results)
          and any(r["status"] == "not_attempted" for r in no_source_results),
          str(no_source_results))

    contradicted_sources = [{
        "claim": "organization_identity", "source_url": "https://registry.example.gov/acme",
        "tier": 1, "contradicts_claim": True, "detail": "Registry lists a different legal entity at this address.",
    }]
    contradicted_results = co.corroborate_claims(claims, same_as_results=[], external_sources=contradicted_sources)
    check("F5 tier-1 contradicting source yields 'contradicted'",
          any(r["status"] == "contradicted" for r in contradicted_results), str(contradicted_results))

    low_tier_sources = [{
        "claim": "organization_identity", "source_url": "https://randomblog.example/post",
        "tier": 3, "contradicts_claim": True, "detail": "A blog post disagrees.",
    }]
    low_tier_results = co.corroborate_claims(claims, same_as_results=[], external_sources=low_tier_sources)
    check("F5 lone tier-3 contradicting source does NOT yield 'contradicted'",
          not any(r["status"] == "contradicted" for r in low_tier_results), str(low_tier_results))

    # --- Proactive P3: sameAs corroboration opportunity ---
    opp_p3 = ar.identify_proactive_opportunities({"pages": FIXTURE_P3_SAMEAS_OPPORTUNITY})
    check("P3 fires: well-specified org name, no sameAs, low ambiguity risk",
          any("sameAs" in o["title"] for o in opp_p3), str(opp_p3))
    check("P3 entry has no 'severity' field (not a defect)",
          opp_p3 and "severity" not in opp_p3[0], str(opp_p3))

    opp_p3_ambiguous = ar.identify_proactive_opportunities({"pages": FIXTURE_P3_AMBIGUOUS_NO_FIRE})
    check("P3 does NOT fire when F2 already flags entity ambiguity (no redundant overlap)",
          opp_p3_ambiguous == [], str(opp_p3_ambiguous))

    opp_p3_has_sameas = ar.identify_proactive_opportunities({"pages": FIXTURE_P3_HAS_SAMEAS})
    check("P3 does NOT fire when sameAs is already present",
          opp_p3_has_sameas == [], str(opp_p3_has_sameas))

    # --- Proactive P4: freshness metadata opportunity ---
    opp_p4 = ar.identify_proactive_opportunities({"pages": FIXTURE_P4_OPPORTUNITY})
    check("P4 fires: >=2 high-sensitivity categories, no dates, no staleness",
          any("freshness metadata" in o["title"].lower() for o in opp_p4), str(opp_p4))
    check("P4 entry has no 'severity' field (not a defect)",
          opp_p4 and "severity" not in opp_p4[0], str(opp_p4))

    opp_p4_single = ar.identify_proactive_opportunities({"pages": FIXTURE_P4_SINGLE_CATEGORY})
    check("P4 does NOT fire on a single incidental high-sensitivity keyword",
          opp_p4_single == [], str(opp_p4_single))

    opp_p4_stale = ar.identify_proactive_opportunities({"pages": FIXTURE_P4_HAS_STALENESS})
    check("P4 does NOT fire when actual staleness evidence is present (F4's territory)",
          opp_p4_stale == [], str(opp_p4_stale))

    opp_p4_has_date = ar.identify_proactive_opportunities({"pages": FIXTURE_P4_HAS_DATEMODIFIED})
    check("P4 does NOT fire when dateModified is already present",
          opp_p4_has_date == [], str(opp_p4_has_date))

    n_pass = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    print(f"\nFIXTURE RESULTS: {n_pass}/{n_total} passed")
    return n_pass, n_total


_BOILERPLATE_ACTIONS = {
    "fix this issue.", "review and fix the problem.", "improve seo.",
    "update the page accordingly.", "investigate and resolve.", "ensure this is correct.",
}


def test_suggested_action_quality(mods):
    """Part 2 regression: every F1-F5 suggested_action is non-empty, not
    generic boilerplate, and mentions remediation content specific to that
    detector. Detection/severity/evidence logic is untouched by Part 2 --
    this only verifies the upgraded suggested_action TEXT.
    """
    print("\n" + "=" * 72 + "\nPART 2 -- SUGGESTED ACTION QUALITY (F1-F5)\n" + "=" * 72)
    ar = mods["audit_runner"]
    ia = mods["identity_analysis"]
    all_ok = True
    by_category: dict[str, list[dict]] = {}

    def _collect(findings):
        for f in findings:
            by_category.setdefault(f.get("category"), []).append(f)

    # F1: identity contradiction across pages.
    _collect(ar.run_freshness_audit({"pages": FIXTURE_IDENTITY_CONTRADICTION}))

    # F2: generic single-word name, no distinguishing signals -> ambiguity risk.
    _collect(ar.run_freshness_audit({"pages": [_page("https://atlas.example/", 200, FIXTURE_AMBIGUOUS_ENTITY_HTML, depth=0)]}))

    # F3: same-entity footer phone contradiction across pages.
    _collect(ar.run_freshness_audit({"pages": FIXTURE_CONTACT_MISMATCH}))

    # F4: expired offer + past-tense-as-present (two of the three staleness sub-types).
    _collect(ar.run_freshness_audit({"pages": [_page("https://event.example/", 200, FIXTURE_STALE_OFFER_HTML, depth=0)]}))

    # F4: dateModified earlier than datePublished (third staleness sub-type).
    date_order_html = ('<html><head><script type="application/ld+json">'
                        '{"@type":"Article","datePublished":"2024-06-01","dateModified":"2024-01-01"}'
                        '</script></head><body><p>Content.</p></body></html>')
    _collect(ar.run_freshness_audit({"pages": [_page("https://biz.example/article", 200, date_order_html, depth=1)]}))

    # F5: contradicted claim (no network -- external_sources are pre-judged verdicts).
    claims_signals = [ia.extract_identity_signals(
        '<html><head><script type="application/ld+json">{"@type":"Organization","name":"Acme Corp"}'
        '</script></head><body><h1>Acme Corp</h1></body></html>', "https://acme.example/")]
    contradicted_sources = [{
        "claim": "organization_identity", "source_url": "https://registry.example.gov/acme",
        "tier": 1, "contradicts_claim": True, "detail": "Registry lists a different legal entity at this address.",
    }]
    _collect(ar._f5_corroboration(claims_signals, contradicted_sources, 5))

    # F5: broken sameAs reference (same invalid-domain convention already used
    # elsewhere in this file's fixture tests -- a DNS-failure lookup, not a
    # real external network dependency).
    broken_signals = [ia.extract_identity_signals(
        '<html><head><script type="application/ld+json">{"@type":"Organization","name":"Acme Corp",'
        '"sameAs":["https://this-domain-should-not-exist-brandaudit-test.invalid/org"]}'
        '</script></head><body><h1>Acme Corp</h1></body></html>', "https://acme.example/")]
    _collect(ar._f5_corroboration(broken_signals, None, 5))

    _EXPECTED_KEYWORDS = {
        "F1": ["alternatename"],
        "F2": ["sameas"],
        "F3": ["phone"],
        "F4": ["datemodified"],
        "F5": ["official profile", "independent source"],
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
        findings = mods["audit_runner"].run_freshness_audit(crawl_result)
        crashed = False
    except Exception as exc:
        import traceback
        traceback.print_exc()
        findings = []
        crashed = True

    duration = round(time.time() - t0, 1)
    print(f"  duration: {duration}s")
    print(f"  findings: {len(findings)}")
    for f in findings:
        print(f"    [{f['severity'].upper()}] {f['category']}: {f['title']}")
        print(f"      Evidence: {f['evidence'][:200]}")

    print(f"\n  PIPELINE CRASH: {'YES (BAD)' if crashed else 'no'}")
    return not crashed, findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--site", default="https://example.com/")
    args = parser.parse_args()

    print("=" * 72)
    print("Brand AI Readiness -- freshness-corroboration Validation (Stage 3)")
    print(f"Python: {sys.version.split()[0]}  |  CWD: {os.getcwd()}")
    print("=" * 72)

    mods = load_all_modules()

    n_pass, n_total = run_fixture_tests(mods)

    action_quality_ok = test_suggested_action_quality(mods)
    if not action_quality_ok:
        print("\nPart 2 suggested_action quality test FAILED")

    live_ok = True
    if not args.skip_live:
        live_ok, _ = run_live_smoke_test(mods, site_url=args.site)

    print("\n" + "=" * 72)
    print("OVERALL RESULT")
    print("=" * 72)
    print(f"Fixture tests: {n_pass}/{n_total} passed")
    print(f"Live smoke test: {'OK' if live_ok else 'CRASHED'}")

    if n_pass != n_total or not live_ok or not action_quality_ok:
        sys.exit(1)
