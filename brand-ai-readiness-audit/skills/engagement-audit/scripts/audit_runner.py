"""
Audit Runner - Main E1-E13 detector engine for the engagement-audit skill.

Orchestrates page-orientation, navigation, CTA, link-health, viewport, and
trust-signal detectors against already-crawled page data (as produced by the
crawl-render-audit skill) and returns a structured list of findings.

Detector coverage:
    E1  - Landing-page orientation
    E2  - Clear next action (merged with E8 quality scoring)
    E4  - Landing-page relevance (also covers what's measurable of E3;
          see module docstring note below)
    E5  - Information findability (click-depth from homepage)
    E6  - Navigation clarity
    E7  - Content hierarchy (narrow structural proxy)
    E8  - CTA quality (see E2)
    E9  - Dead ends
    E10 - Broken engagement elements
    E11 - Mobile/viewport usability
    E12 - Intrusive interruption
    E13 - Trust/confidence signals

Note on E3 (Context Retention): as specified in SKILL.md, E3 requires
knowing the actual query that brought a visitor to the page, which a static
website audit has no access to. It is not implemented as an independent
detector; E4's URL-implied-topic-vs-content check is the closest
deterministically measurable proxy and covers it to the extent possible.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .page_orientation import assess_orientation
from .navigation_analysis import analyze_navigation
from .cta_analysis import analyze_ctas
from .link_health import check_links
from .viewport_check import check_viewport, compare_viewports, is_playwright_available
from .engagement_analysis import assess_trust_signals, detect_intrusive_interruptions

log = logging.getLogger(__name__)

_PAGE_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pricing": ("pricing", "plans", "plan"),
    "product": ("product", "shop", "store", "item"),
    "about": ("about", "company", "team"),
    "contact": ("contact",),
    "blog": ("blog", "article", "post", "news"),
    "docs": ("docs", "documentation", "guide"),
    "faq": ("faq", "help"),
    "service": ("service", "solutions"),
}

_COMMERCIAL_TYPES = {"product", "pricing", "service"}
_TARGET_DEPTH_LIMITS = {"contact": 2, "pricing": 2, "docs": 2}
_GENERIC_SEGMENTS = {"index", "home", "page", "default", "main"}
_ACTION_DEMANDING_KEYWORDS = (
    "sign up", "subscribe", "email", "newsletter", "join", "register", "create an account",
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_engagement_audit(
    crawl_result: dict[str, Any],
    max_link_checks: int = 20,
    max_viewport_pages: int = 2,
    render_comparisons: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run all E1-E13 detectors and return a list of findings.

    Args:
        crawl_result: Output from crawl.bounded_crawl() with a 'pages' key
            (as produced by the crawl-render-audit skill). Reused as-is —
            this skill does not perform its own crawling.
        max_link_checks: Bound on new HTTP HEAD requests for E10 (link
            destinations not already covered by the crawl itself).
        max_viewport_pages: Bound on Playwright viewport checks for E11.
        render_comparisons: Optional raw-vs-rendered comparison data (from
            crawl-render-audit's shared render pass). Every detector here
            except E11 only ever looks at raw HTML — on a page where JS
            renders in most of the real content, that raw HTML is not
            representative, and several checks would otherwise report
            content as "missing" purely because it hasn't loaded yet
            (confirmed on a real unseen site in Stage 7). Pages flagged
            here as a "significant_gap", or that returned an HTTP error
            status (e.g. a bot-block or 404 page rather than real content,
            also confirmed in the same test), are excluded from those
            checks rather than guessed at.

    Returns:
        List of finding dicts with title, severity, category, evidence,
        and suggested_action.
    """
    pages: list[dict[str, Any]] = crawl_result.get("pages", [])
    if not pages:
        return []

    homepage_url = _find_homepage(pages)
    crawled_status = {(p.get("final_url") or p.get("url", "")): p.get("status") for p in pages}
    page_data = _analyse_all_pages(pages)
    js_heavy_urls = {c.get("url") for c in (render_comparisons or []) if c.get("significant_gap")}
    error_page_urls = {
        (p.get("final_url") or p.get("url", "")) for p in pages
        if p.get("status") and p.get("status") >= 400
    }
    unreliable_urls = js_heavy_urls | error_page_urls

    findings: list[dict[str, Any]] = []
    findings += _e1_orientation(page_data, homepage_url, unreliable_urls)
    findings += _e2_e8_cta_quality(page_data, unreliable_urls)
    findings += _e4_url_content_alignment(page_data, unreliable_urls)
    findings += _e5_findability(pages, page_data, homepage_url)
    findings += _e6_navigation_clarity(pages, homepage_url)
    findings += _e7_content_hierarchy(page_data, unreliable_urls)
    findings += _e9_dead_ends(page_data, unreliable_urls)
    findings += _e10_broken_engagement_elements(page_data, crawled_status, max_link_checks)
    findings += _e11_viewport(page_data, homepage_url, max_viewport_pages)
    findings += _e12_intrusive_interruptions(page_data)
    findings += _e13_trust_signals(page_data)

    return findings


# ---------------------------------------------------------------------------
# Per-page signal extraction
# ---------------------------------------------------------------------------


def _find_homepage(pages: list[dict[str, Any]]) -> str:
    for p in pages:
        if p.get("depth", 1) == 0:
            return p.get("final_url") or p.get("url", "")
    return pages[0].get("url", "") if pages else ""


def _classify_page_type(url: str, depth: int) -> str:
    if depth == 0:
        return "homepage"
    path = urlparse(url).path.lower()
    for ptype, keywords in _PAGE_TYPE_KEYWORDS.items():
        if any(kw in path for kw in keywords):
            return ptype
    return "generic"


def _structural_signals(html: str) -> dict[str, Any]:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return {"text_length": 0, "has_subheadings": False}
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    has_subheadings = bool(soup.find(["h2", "h3"]))
    return {"text_length": len(text), "has_subheadings": has_subheadings}


def _count_continuation_links(html: str, url: str) -> int:
    """Count internal links outside the primary <nav> element.

    Footer/body links count as valid continuation paths (per E9's own
    definition); only the main navigation is excluded, since its presence
    is already assessed separately (E6).
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return 0
    domain = urlparse(url).netloc
    nav_link_ids = {id(a) for nav in soup.find_all("nav") for a in nav.find_all("a", href=True)}
    seen: set[str] = set()
    count = 0
    for a in soup.find_all("a", href=True):
        if id(a) in nav_link_ids:
            continue
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(url, href).split("#")[0]
        if urlparse(absolute).netloc != domain or absolute in seen:
            continue
        seen.add(absolute)
        count += 1
    return count


def _analyse_all_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    analyses = []
    for page in pages:
        url = page.get("final_url") or page.get("url", "")
        html = page.get("body", "") or ""
        depth = page.get("depth", 1)
        try:
            orientation = assess_orientation(html, url)
        except Exception as exc:
            log.warning("assess_orientation failed for %s: %s", url, exc)
            orientation = {}
        try:
            ctas = analyze_ctas(html, url)
        except Exception as exc:
            log.warning("analyze_ctas failed for %s: %s", url, exc)
            ctas = {"total_ctas": 0, "ctas": [], "generic_count": 0, "specific_count": 0, "has_primary_cta": False}
        try:
            interruptions = detect_intrusive_interruptions(html, url)
        except Exception as exc:
            log.warning("detect_intrusive_interruptions failed for %s: %s", url, exc)
            interruptions = []
        try:
            trust = assess_trust_signals(html, url)
        except Exception as exc:
            log.warning("assess_trust_signals failed for %s: %s", url, exc)
            trust = {}

        analyses.append({
            "url": url,
            "depth": depth,
            "page_type": _classify_page_type(url, depth),
            "orientation": orientation,
            "ctas": ctas,
            "structural": _structural_signals(html),
            "continuation_links": _count_continuation_links(html, url),
            "interruptions": interruptions,
            "trust": trust,
        })
    return analyses


# ---------------------------------------------------------------------------
# E1 - Landing-Page Orientation
# ---------------------------------------------------------------------------


def _e1_orientation(
    page_data: list[dict[str, Any]], homepage_url: str, unreliable_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    problems = [
        pd for pd in page_data
        if pd["page_type"] != "generic" and pd["orientation"]
        and not pd["orientation"].get("has_h1") and not pd["orientation"].get("org_identity_visible")
        and pd["url"] not in unreliable_urls
    ]
    if not problems:
        return []

    lines = [f"- `{p['url']}` ({p['page_type']})" for p in problems[:5]]
    severity = "high" if any(p["url"] == homepage_url for p in problems) else "medium"
    evidence = f"{len(problems)} important page(s) have no H1 and no visible organization identity:\n" + "\n".join(lines)

    return [{
        "title": f"{len(problems)} important page(s) lack basic orientation cues",
        "severity": severity,
        "category": "E1",
        "evidence": evidence,
        "suggested_action": {
            "summary": "Add a clear H1 and visible organization identity (logo/header) so a visitor landing directly on the page understands what it is.",
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# E2 / E8 - Clear Next Action / CTA Quality
# ---------------------------------------------------------------------------


def _e2_e8_cta_quality(
    page_data: list[dict[str, Any]], unreliable_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    key_pages = [pd for pd in page_data if pd["page_type"] in ("pricing", "product", "service")]
    no_cta = [pd for pd in key_pages if pd["ctas"].get("total_ctas", 0) == 0 and pd["url"] not in unreliable_urls]
    generic_only = [
        pd for pd in key_pages
        if pd["ctas"].get("total_ctas", 0) > 0
        and pd["ctas"].get("generic_count", 0) > 0
        and pd["ctas"].get("specific_count", 0) == 0
    ]

    findings = []
    if no_cta:
        lines = [f"- `{p['url']}` ({p['page_type']})" for p in no_cta[:5]]
        findings.append({
            "title": f"{len(no_cta)} key page(s) have no clear next-step CTA",
            "severity": "high",
            "category": "E2",
            "evidence": f"{len(no_cta)} pricing/product/service page(s) have zero CTAs:\n" + "\n".join(lines),
            "suggested_action": {
                "summary": "Add a clear, specific CTA (e.g. 'Start Free Trial', 'Book a Demo') to this page.",
                "priority": "high",
            },
        })
    if generic_only:
        lines = [
            f"- `{p['url']}`: " + ", ".join(f"'{c['text']}'" for c in p["ctas"]["ctas"][:3])
            for p in generic_only[:5]
        ]
        findings.append({
            "title": f"{len(generic_only)} key page(s) use only generic CTA text",
            "severity": "medium",
            "category": "E8",
            "evidence": f"{len(generic_only)} page(s) have CTAs but all are generic:\n" + "\n".join(lines),
            "suggested_action": {
                "summary": "Replace generic CTA text ('Learn More', 'Click Here') with specific action text describing what happens next.",
                "priority": "medium",
            },
        })
    return findings


# ---------------------------------------------------------------------------
# E4 - Landing-Page Relevance (covers the measurable part of E3)
# ---------------------------------------------------------------------------


def _last_meaningful_segment(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    segment = path.split("/")[-1]
    segment = re.sub(r"\.(html?|php|aspx?)$", "", segment, flags=re.IGNORECASE)
    if not segment or segment.isdigit() or segment.lower() in _GENERIC_SEGMENTS or len(segment) <= 2:
        return None
    words = [w for w in re.split(r"[-_]+", segment) if w and not w.isdigit()]
    if not words:
        return None
    return " ".join(words)


def _e4_url_content_alignment(
    page_data: list[dict[str, Any]], unreliable_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    problems = []
    for pd in page_data:
        if pd["depth"] == 0:
            continue  # homepage has no single "implied topic" to check against
        if pd["url"] in unreliable_urls:
            continue  # raw H1/title aren't representative of this page's real content
        phrase = _last_meaningful_segment(pd["url"])
        if not phrase:
            continue
        orient = pd["orientation"]
        h1_text = " ".join(orient.get("h1_content", []) or []).lower()
        title_text = (orient.get("title") or "").lower()
        combined = f"{h1_text} {title_text}"

        # Concatenated (space-free) form of the URL segment. Checking
        # against this, rather than requiring the segment's own first
        # "word" to appear verbatim in the text, is what lets this work for
        # BOTH hyphenated slugs ("analytics-suite" -> "analyticssuite") AND
        # concatenated slugs with no delimiter at all ("howitworks") --
        # the latter previously could never match anything, since its
        # "first word" was the entire unsplit blob (confirmed as a real
        # false positive on an unseen site).
        concatenated_segment = phrase.lower().replace(" ", "")
        significant_words = [w for w in re.findall(r"[a-z0-9]+", combined) if len(w) >= 4]
        if not any(w in concatenated_segment for w in significant_words):
            problems.append({"url": pd["url"], "segment": phrase})

    if not problems:
        return []

    lines = [f"- `{p['url']}`: URL implies '{p['segment']}' but neither H1 nor title mention it." for p in problems[:5]]
    return [{
        "title": f"{len(problems)} page(s) don't visibly match what their URL implies",
        "severity": "medium",
        "category": "E4",
        "evidence": f"{len(problems)} page(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": (
                "Update this page's `<h1>` and `<title>` to reflect the topic implied by its URL segment "
                "(or correct the URL/redirect if the segment no longer matches the page's actual content), "
                "then verify the rendered H1/title mention it."
            ),
            "priority": "medium",
        },
    }]


# ---------------------------------------------------------------------------
# E5 - Information Findability
# ---------------------------------------------------------------------------


def _build_internal_graph(pages: list[dict[str, Any]]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for page in pages:
        url = page.get("final_url") or page.get("url", "")
        html = page.get("body", "") or ""
        domain = urlparse(url).netloc
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            graph[url] = []
            continue
        targets: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            absolute = urljoin(url, href).split("#")[0]
            if urlparse(absolute).netloc != domain or absolute in seen:
                continue
            seen.add(absolute)
            targets.append(absolute)
        graph[url] = targets
    return graph


def _bfs_depths(graph: dict[str, list[str]], start: str) -> dict[str, int]:
    from collections import deque
    depths = {start: 0}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, []):
            if target not in depths and target in graph:
                depths[target] = depths[current] + 1
                queue.append(target)
    return depths


def _e5_findability(
    pages: list[dict[str, Any]],
    page_data: list[dict[str, Any]],
    homepage_url: str,
) -> list[dict[str, Any]]:
    graph = _build_internal_graph(pages)
    if homepage_url not in graph:
        return []
    depths = _bfs_depths(graph, homepage_url)

    problems = []
    for pd in page_data:
        limit = _TARGET_DEPTH_LIMITS.get(pd["page_type"])
        if limit is None:
            continue
        depth = depths.get(pd["url"])
        if depth is not None and depth > limit:
            problems.append({"url": pd["url"], "type": pd["page_type"], "depth": depth})

    if not problems:
        return []

    lines = [f"- `{p['url']}` ({p['type']}) is {p['depth']} hops from the homepage" for p in problems[:5]]
    severity = "medium" if any(p["depth"] > 3 for p in problems) else "low"
    return [{
        "title": f"{len(problems)} important page(s) are hard to find (deep click-path from homepage)",
        "severity": severity,
        "category": "E5",
        "evidence": f"{len(problems)} page(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": "Add a direct navigation or homepage link so visitors can reach this page within 1-2 clicks.",
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# E6 - Navigation Clarity
# ---------------------------------------------------------------------------


def _e6_navigation_clarity(pages: list[dict[str, Any]], homepage_url: str) -> list[dict[str, Any]]:
    homepage_page = next((p for p in pages if (p.get("final_url") or p.get("url", "")) == homepage_url), None)
    if not homepage_page:
        return []
    try:
        nav = analyze_navigation(homepage_page.get("body", "") or "", homepage_url)
    except Exception:
        return []

    ambiguous = nav.get("label_assessment", [])
    # Ambiguity matters more in a small menu, where each label carries more
    # weight; a large mega-menu with one loosely-worded item is not flagged.
    if not ambiguous or nav.get("nav_link_count", 0) > 6:
        return []

    lines = [f"- '{a['text']}': {a['note']}" for a in ambiguous[:5]]
    return [{
        "title": "Navigation contains ambiguous label(s) in a small menu",
        "severity": "low",
        "category": "E6",
        "evidence": f"Homepage nav has only {nav.get('nav_link_count')} link(s), including ambiguous label(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": "Use more descriptive navigation labels (e.g. 'Pricing' instead of 'Solutions'), especially in a small menu where each label carries more weight.",
            "priority": "low",
        },
    }]


# ---------------------------------------------------------------------------
# E7 - Content Hierarchy (narrow structural proxy)
# ---------------------------------------------------------------------------


def _e7_content_hierarchy(
    page_data: list[dict[str, Any]], unreliable_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    problems = [
        pd for pd in page_data
        if pd["page_type"] != "generic"
        and pd["structural"].get("text_length", 0) > 200
        and not pd["structural"].get("has_subheadings")
        and pd["ctas"].get("total_ctas", 0) == 0
        and pd["continuation_links"] == 0
        and pd["url"] not in unreliable_urls
    ]
    if not problems:
        return []

    lines = [
        f"- `{p['url']}`: {p['structural']['text_length']} chars of text, no H2/H3 sub-headings, no CTA, no continuation links"
        for p in problems[:5]
    ]
    return [{
        "title": f"{len(problems)} page(s) present unstructured content with no next step",
        "severity": "low",
        "category": "E7",
        "evidence": f"{len(problems)} page(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": (
                "Break this page's long block of text into sections with `<h2>`/`<h3>` sub-headings and "
                "add at least one link or CTA for what to do next, then verify both appear in the "
                "rendered page."
            ),
            "priority": "low",
        },
    }]


# ---------------------------------------------------------------------------
# E9 - Dead Ends
# ---------------------------------------------------------------------------


def _e9_dead_ends(
    page_data: list[dict[str, Any]], unreliable_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    problems = [
        pd for pd in page_data
        if pd["page_type"] != "generic"
        and pd["ctas"].get("total_ctas", 0) == 0
        and pd["continuation_links"] == 0
        and pd["url"] not in unreliable_urls
    ]
    if not problems:
        return []

    lines = [f"- `{p['url']}` ({p['page_type']})" for p in problems[:5]]
    return [{
        "title": f"{len(problems)} important page(s) are dead ends",
        "severity": "medium",
        "category": "E9",
        "evidence": f"{len(problems)} page(s) have no CTA and no other internal links to continue to:\n" + "\n".join(lines),
        "suggested_action": {
            "summary": "Add at least one link (related content, footer, or CTA) so visitors have a next step.",
            "priority": "medium",
        },
    }]


# ---------------------------------------------------------------------------
# E10 - Broken Engagement Elements
# ---------------------------------------------------------------------------


def _e10_broken_engagement_elements(
    page_data: list[dict[str, Any]],
    crawled_status: dict[str, Any],
    max_link_checks: int,
) -> list[dict[str, Any]]:
    all_ctas = []
    for pd in page_data:
        for c in pd["ctas"].get("ctas", []):
            href = c.get("href", "")
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                all_ctas.append((pd["url"], pd["page_type"], c))

    if not all_ctas:
        return []

    to_check: list[dict[str, str]] = []
    reused_status: dict[str, Any] = {}
    seen_hrefs: set[str] = set()
    for page_url, _ptype, c in all_ctas:
        absolute = urljoin(page_url, c["href"]).split("#")[0]
        if absolute in seen_hrefs:
            continue
        seen_hrefs.add(absolute)
        if absolute in crawled_status:
            reused_status[absolute] = crawled_status[absolute]
        else:
            to_check.append({"href": absolute, "text": c.get("text", "")})

    checked_results = check_links(to_check, max_checks=max_link_checks) if to_check else []
    broken_hrefs = {r["href"] for r in checked_results if r.get("is_broken")}
    for href, status in reused_status.items():
        if status and status >= 400:
            broken_hrefs.add(href)

    problems = []
    for page_url, ptype, c in all_ctas:
        absolute = urljoin(page_url, c["href"]).split("#")[0]
        if absolute in broken_hrefs:
            problems.append({"page_url": page_url, "page_type": ptype, "cta_text": c.get("text", ""), "href": absolute})

    if not problems:
        return []

    lines = [f"- `{p['page_url']}`: CTA '{p['cta_text']}' -> `{p['href']}`" for p in problems[:5]]
    severity = "high" if any(p["page_type"] in ("pricing", "product", "service") for p in problems) else "medium"
    return [{
        "title": f"{len(problems)} CTA(s)/link(s) lead to broken destinations",
        "severity": severity,
        "category": "E10",
        "evidence": f"{len(problems)} broken engagement element(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": (
                "Fix the destination URL or remove the CTA/link identified above, then verify it now "
                "returns HTTP 200 (or redirects to a working page)."
            ),
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# E11 - Mobile/Viewport Usability
# ---------------------------------------------------------------------------


def _e11_viewport(
    page_data: list[dict[str, Any]],
    homepage_url: str,
    max_viewport_pages: int,
) -> list[dict[str, Any]]:
    if not is_playwright_available():
        return []

    candidates = [homepage_url] if homepage_url else []
    for pd in page_data:
        if len(candidates) >= max_viewport_pages:
            break
        if pd["url"] != homepage_url and pd["page_type"] != "generic":
            candidates.append(pd["url"])
    candidates = candidates[:max_viewport_pages]

    overflow_pages = []
    disappear_pages = []
    for url in candidates:
        try:
            vp = check_viewport(url)
        except Exception as exc:
            log.warning("check_viewport failed for %s: %s", url, exc)
            continue
        if vp.get("error") or not vp.get("playwright_available"):
            continue
        desktop, mobile = vp.get("desktop", {}), vp.get("mobile", {})
        for issue in mobile.get("issues", []):
            if issue["type"] == "horizontal_overflow":
                overflow_pages.append({"url": url, "detail": issue["detail"]})
        for issue in compare_viewports(desktop, mobile):
            disappear_pages.append({"url": url, "detail": issue["detail"]})

    findings = []
    if overflow_pages:
        lines = [f"- `{p['url']}`: {p['detail']}" for p in overflow_pages[:5]]
        findings.append({
            "title": f"{len(overflow_pages)} page(s) have horizontal overflow at mobile width",
            "severity": "medium",
            "category": "E11",
            "evidence": f"{len(overflow_pages)} page(s):\n" + "\n".join(lines),
            "suggested_action": {
                "summary": "Fix responsive CSS so content fits within the mobile viewport without horizontal scrolling.",
                "priority": "medium",
            },
        })
    if disappear_pages:
        lines = [f"- `{p['url']}`: {p['detail']}" for p in disappear_pages[:5]]
        findings.append({
            "title": f"{len(disappear_pages)} page(s) lose navigation or CTA visibility on mobile",
            "severity": "high",
            "category": "E11",
            "evidence": f"{len(disappear_pages)} page(s):\n" + "\n".join(lines),
            "suggested_action": {
                "summary": "Ensure primary navigation and CTA remain visible and tappable at mobile viewport widths.",
                "priority": "high",
            },
        })
    return findings


# ---------------------------------------------------------------------------
# E12 - Intrusive Interruption
# ---------------------------------------------------------------------------


def _e12_intrusive_interruptions(page_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Keyed by page URL so the finding count reflects affected PAGES, not
    # the number of matching signals/keywords (confirmed on a real unseen
    # site: a single element matching several keywords, or several elements
    # on one page, must not inflate "N page(s)").
    page_matches: dict[str, list[dict[str, str]]] = {}
    for pd in page_data:
        seen_texts: set[str] = set()
        for sig in pd["interruptions"]:
            matched = set(sig.get("matched_keywords") or ([sig["type"]] if sig.get("type") else []))
            text = (sig.get("text_preview", "") or "")
            text_key = text.lower()[:120]
            # Only promote to a finding when the element looks genuinely
            # blocking (modal/interstitial) or explicitly demands an action
            # (signup/newsletter capture) — a small dismissible banner is
            # never enough on its own.
            if matched & {"modal", "interstitial"} or any(k in text.lower() for k in _ACTION_DEMANDING_KEYWORDS):
                if text_key in seen_texts:
                    continue  # same interruption already recorded for this page
                seen_texts.add(text_key)
                page_matches.setdefault(pd["url"], []).append({"type": sig.get("type", ""), "text": text[:120]})

    if not page_matches:
        return []

    affected_urls = list(page_matches.keys())
    lines = []
    for url in affected_urls[:5]:
        for m in page_matches[url][:2]:  # at most 2 distinct interruption texts per page
            lines.append(f"- `{url}` ({m['type']}): \"{m['text']}\"")
    severity = "high" if any(m["type"] == "modal" for matches in page_matches.values() for m in matches) else "medium"
    return [{
        "title": f"{len(affected_urls)} page(s) show intrusive interruptions",
        "severity": severity,
        "category": "E12",
        "evidence": f"{len(affected_urls)} page(s):\n" + "\n".join(lines),
        "suggested_action": {
            "summary": "Remove or make easily dismissible full-screen modals/signup walls that block access to page content.",
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# E13 - Trust/Confidence Signals
# ---------------------------------------------------------------------------


def _e13_trust_signals(page_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    is_commercial = any(pd["page_type"] in _COMMERCIAL_TYPES for pd in page_data)
    if not is_commercial:
        return []

    aggregate = {"has_contact_info": False, "has_about_info": False, "has_privacy_policy": False, "has_terms": False}
    for pd in page_data:
        trust = pd["trust"]
        for key in aggregate:
            if trust.get(key):
                aggregate[key] = True

    present_count = sum(1 for v in aggregate.values() if v)
    if present_count > 1:
        return []

    missing = [k.replace("has_", "").replace("_", " ") for k, v in aggregate.items() if not v]
    return [{
        "title": "Site shows few trust/confidence signals for a commercial offering",
        "severity": "medium",
        "category": "E13",
        "evidence": f"Across {len(page_data)} crawled page(s), only {present_count}/4 trust signal categories were found. Missing: {', '.join(missing)}.",
        "suggested_action": {
            "summary": (
                f"Add the missing trust signal(s) noted above ({', '.join(missing)}) so visitors can "
                f"verify who is behind this site."
            ),
            "priority": "medium",
        },
    }]


# ---------------------------------------------------------------------------
# Proactive opportunities (not defects) — evidence-gated, non-overlapping
# with E1-E13. Kept separate from findings: these are enhancement
# suggestions, never a claim that something is broken.
# ---------------------------------------------------------------------------


def identify_proactive_opportunities(
    crawl_result: dict[str, Any],
    render_comparisons: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Identify a breadcrumb opportunity (P5) that is not a defect.

    Reuses the same per-page analysis (_analyse_all_pages) and the same
    unreliable-URL gating (JS-heavy/error pages) run_engagement_audit
    already computes — no new crawling/rendering.

    Fires only for pages that are genuinely deep in the site (depth >= 2,
    matching the same "substantial real content" gate E7/E9 already use for
    text_length > 200) and have no breadcrumb trail at all (neither visible
    navigation nor BreadcrumbList schema, per assess_orientation). This does
    not overlap E1 (H1/org-identity orientation), E5/E6 (findability/nav
    clarity), or E7 (unstructured content) — none of those check breadcrumb
    presence.
    """
    pages: list[dict[str, Any]] = crawl_result.get("pages", [])
    if not pages:
        return []

    page_data = _analyse_all_pages(pages)
    js_heavy_urls = {c.get("url") for c in (render_comparisons or []) if c.get("significant_gap")}
    error_page_urls = {
        (p.get("final_url") or p.get("url", "")) for p in pages
        if p.get("status") and p.get("status") >= 400
    }
    unreliable_urls = js_heavy_urls | error_page_urls

    problems = [
        pd for pd in page_data
        if pd.get("depth", 0) >= 2
        and pd["structural"].get("text_length", 0) > 200
        and pd["url"] not in unreliable_urls
        and not pd["orientation"].get("has_breadcrumbs")
    ]
    if not problems:
        return []

    lines = [f"- `{p['url']}` (depth {p['depth']})" for p in problems[:5]]
    return [{
        "title": f"{len(problems)} deep page(s) have no breadcrumb trail",
        "evidence": (
            f"{len(problems)} page(s) are several levels deep in the site structure with substantial "
            f"content but no breadcrumb navigation or BreadcrumbList schema:\n" + "\n".join(lines)
        ),
        "suggested_action": {
            "summary": (
                "Adding a breadcrumb trail (visible navigation or BreadcrumbList schema) gives visitors "
                "clearer hierarchical context and provides an additional structured, machine-readable "
                "representation of the page's position in your site. It is not a guaranteed ranking or "
                "citation factor, just a structural clarity improvement."
            ),
            "priority": "low",
        },
    }]
