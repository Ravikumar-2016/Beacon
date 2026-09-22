"""
Audit Runner - Main C1-C12 detector engine for the crawl-render-audit skill.

Orchestrates all twelve detectors against crawled page data and returns
a structured list of findings. Each detector produces signals; signals are
promoted to findings only when they represent genuine discoverability problems.

Detector coverage:
    C1  - Crawl permission (robots.txt)
    C2  - HTTP accessibility
    C3  - Redirect chains
    C4  - Raw vs rendered HTML
    C5  - Machine-readable content
    C6  - Structured data presence
    C7  - Structured data consistency
    C8  - Robots meta / X-Robots-Tag
    C9  - Crawlable internal links
    C10 - Canonical consistency
    C11 - Page title / metadata
    C12 - Heading / document structure
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from .html_analysis import analyze_html, detect_loading_placeholders
from .link_analysis import (
    analyze_nav_coverage,
    build_link_graph,
    extract_links,
    find_disconnected_pages,
    find_orphan_pages,
    normalize_url,
)
from .metadata_analysis import assess_title_quality, extract_metadata, is_indexing_blocked
from .structured_data import check_consistency, extract_all_structured_data, assess_page_schema_need

log = logging.getLogger(__name__)

_IMPORTANT_PATH_KEYWORDS = ("product", "service", "about", "contact", "pricing", "blog", "faq")
AI_AGENTS_DISPLAY = ("*", "Googlebot", "GPTBot", "Google-Extended", "anthropic-ai", "Claude-Web")
MAX_ACCEPTABLE_REDIRECTS = 3
RENDER_DIFF_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_crawl_audit(
    crawl_result: dict[str, Any],
    robots_data: dict[str, Any] | None = None,
    render_comparisons: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run all C1-C12 detectors and return a list of findings.

    Args:
        crawl_result: Output from crawl.bounded_crawl() with keys:
            pages, sitemap_urls, urls_discovered, urls_crawled, errors.
        robots_data: Output from robots_check.fetch_robots_txt() or None.
        render_comparisons: List of render comparison dicts or None.

    Returns:
        List of finding dicts with title, severity, category, evidence,
        and suggested_action.
    """
    pages: list[dict[str, Any]] = crawl_result.get("pages", [])
    sitemap_urls: list[str] = crawl_result.get("sitemap_urls", [])
    crawl_errors: list[dict[str, Any]] = crawl_result.get("errors", [])

    if not pages and not crawl_errors:
        return [{
            "title": "No pages crawled",
            "severity": "critical",
            "category": "crawl",
            "evidence": "The crawler returned no pages. The site may be unreachable.",
            "suggested_action": {
                "summary": "Verify the site URL is correct and the site is publicly accessible.",
                "priority": "critical",
            },
        }]

    findings: list[dict[str, Any]] = []
    homepage_url = _find_homepage(pages, crawl_result)
    page_analyses = _analyse_all_pages(pages)

    link_graph = build_link_graph(
        [{"url": p["url"], "links": pa.get("links", {})} for p, pa in zip(pages, page_analyses)]
    )
    all_known_urls = set(sitemap_urls) | {p["url"] for p in pages}

    # Pages where raw HTML is known to be substantially incomplete (JS
    # renders in most of the real content). Raw-HTML-only checks below use
    # this to avoid concluding something is "missing"/"inconsistent" when
    # the truth is simply that the raw HTML isn't representative of what a
    # real visitor (or a rendering-capable crawler) would see.
    js_heavy_urls = {c.get("url") for c in (render_comparisons or []) if c.get("significant_gap")}

    findings += _c1_crawl_permission(robots_data, pages, sitemap_urls)
    findings += _c2_http_accessibility(pages, crawl_errors)
    findings += _c3_redirect_chains(pages)
    if render_comparisons:
        findings += _c4_raw_vs_rendered(render_comparisons)
    findings += _c5_machine_readable(pages, page_analyses)
    findings += _c6_structured_data_presence(pages, page_analyses)
    findings += _c7_structured_data_consistency(pages, page_analyses, js_heavy_urls)
    findings += _c8_robots_meta(pages, page_analyses)
    findings += _c9_crawlable_links(link_graph, all_known_urls, homepage_url, pages, page_analyses)
    findings += _c10_canonical_consistency(pages, page_analyses, all_known_urls)
    findings += _c11_page_title_metadata(pages, page_analyses)
    findings += _c12_heading_structure(pages, page_analyses)

    return findings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_homepage(pages: list[dict[str, Any]], crawl_result: dict[str, Any]) -> str:
    for p in pages:
        if p.get("depth", 1) == 0:
            return p.get("final_url") or p.get("url", "")
    return pages[0].get("url", "") if pages else ""


def _analyse_all_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    analyses = []
    for page in pages:
        html = page.get("body", "") or ""
        url = page.get("final_url") or page.get("url", "")
        headers = {k.lower(): v for k, v in (page.get("headers") or {}).items()}
        analysis: dict[str, Any] = {}
        try:
            analysis["html"] = analyze_html(html, url)
        except Exception as exc:
            log.warning("html_analysis failed for %s: %s", url, exc)
            analysis["html"] = {}
        try:
            analysis["metadata"] = extract_metadata(html, url, headers)
        except Exception as exc:
            log.warning("metadata_analysis failed for %s: %s", url, exc)
            analysis["metadata"] = {}
        try:
            analysis["structured_data"] = extract_all_structured_data(html)
        except Exception as exc:
            log.warning("structured_data failed for %s: %s", url, exc)
            analysis["structured_data"] = {}
        try:
            analysis["links"] = extract_links(html, url)
        except Exception as exc:
            log.warning("link extraction failed for %s: %s", url, exc)
            analysis["links"] = {}
        try:
            analysis["loading_placeholders"] = detect_loading_placeholders(html)
        except Exception as exc:
            log.warning("placeholder detection failed for %s: %s", url, exc)
            analysis["loading_placeholders"] = []
        analyses.append(analysis)
    return analyses


# ---------------------------------------------------------------------------
# C1 - Crawl Permission (robots.txt)
# ---------------------------------------------------------------------------


def _c1_crawl_permission(
    robots_data: dict[str, Any] | None,
    pages: list[dict[str, Any]],
    sitemap_urls: list[str],
) -> list[dict[str, Any]]:
    if not robots_data or not robots_data.get("exists"):
        return []
    parser = robots_data.get("parser")
    if parser is None:
        return []

    important_urls = [
        u for u in set(sitemap_urls) | {p.get("url", "") for p in pages}
        if any(kw in u.lower() for kw in _IMPORTANT_PATH_KEYWORDS)
    ]

    blocked_by_url: dict[str, list[str]] = {}
    for url in important_urls:
        for ua in AI_AGENTS_DISPLAY:
            if not parser.can_fetch(ua, url):
                blocked_by_url.setdefault(url, []).append(ua)

    if not blocked_by_url:
        return []

    example_url, example_agents = next(iter(blocked_by_url.items()))
    agents_str = ", ".join(f"`{a}`" for a in example_agents[:3])
    evidence = (
        f"robots.txt blocks {len(blocked_by_url)} important URL(s). "
        f"Example: `{example_url}` blocked for {agents_str}."
    )
    if len(blocked_by_url) > 1:
        more = list(blocked_by_url.keys())[1:4]
        evidence += f" Also: {', '.join(more)}"

    return [{
        "title": "robots.txt blocks important public content from AI crawlers",
        "severity": "high",
        "category": "C1",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Review robots.txt Disallow rules and remove restrictions on important public pages. "
                "Ensure GPTBot, anthropic-ai, and Googlebot can access key content."
            ),
            "priority": "high",
        },
    }]


# ---------------------------------------------------------------------------
# C2 - HTTP Accessibility
# ---------------------------------------------------------------------------


def _c2_http_accessibility(
    pages: list[dict[str, Any]],
    crawl_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    broken: list[dict[str, Any]] = []
    for page in pages:
        status = page.get("status")
        url = page.get("url", "")
        if status and status >= 400:
            broken.append({"url": url, "issue": f"HTTP {status}"})
    for err in crawl_errors:
        broken.append({"url": err.get("url", ""), "issue": err.get("error", "unknown error")})

    if not broken:
        return []

    important_broken = [
        b for b in broken
        if any(kw in b["url"].lower() for kw in _IMPORTANT_PATH_KEYWORDS)
    ] or broken

    examples = important_broken[:5]
    evidence_lines = [f"- `{b['url']}`: {b['issue']}" for b in examples]
    evidence = f"{len(important_broken)} important page(s) are inaccessible:\n" + "\n".join(evidence_lines)
    if len(important_broken) > 5:
        evidence += f"\n...and {len(important_broken) - 5} more."

    severity = "critical" if any(b["issue"] == "timeout" for b in important_broken) else "high"

    return [{
        "title": f"{len(important_broken)} important page(s) are inaccessible (HTTP errors or timeouts)",
        "severity": severity,
        "category": "C2",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Resolve each URL's HTTP error or timeout above -- restore the page, fix the underlying "
                "server issue, or add a 301 redirect to its replacement -- then verify it returns HTTP 200 "
                "(or an intentional 3xx)."
            ),
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# C3 - Redirect Chains
# ---------------------------------------------------------------------------


def _c3_redirect_chains(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loops = []
    long_chains = []

    for page in pages:
        redirects = page.get("redirects", []) or []
        url = page.get("url", "")
        final_url = page.get("final_url", url)
        if not redirects:
            continue

        chain_urls = [r.get("url", "") for r in redirects] + [final_url]
        if len(chain_urls) != len(set(chain_urls)):
            loops.append({"url": url, "detail": f"Loop in chain of {len(redirects)} hops."})
        elif len(redirects) > MAX_ACCEPTABLE_REDIRECTS:
            long_chains.append({"url": url, "detail": f"{len(redirects)} hops: {url} -> {final_url}"})

    findings = []
    if loops:
        evidence = f"{len(loops)} redirect loop(s):\n" + "\n".join(f"- `{p['url']}`: {p['detail']}" for p in loops[:3])
        findings.append({
            "title": f"{len(loops)} redirect loop(s) detected",
            "severity": "high",
            "category": "C3",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Point the redirect directly at its final destination instead of back into the chain, "
                    "then verify the URL now resolves in a single hop."
                ),
                "priority": "high",
            },
        })
    if long_chains:
        evidence = f"{len(long_chains)} page(s) with >{MAX_ACCEPTABLE_REDIRECTS} redirect hops:\n"
        evidence += "\n".join(f"- `{p['url']}`: {p['detail']}" for p in long_chains[:5])
        findings.append({
            "title": f"{len(long_chains)} page(s) have excessively long redirect chains",
            "severity": "medium",
            "category": "C3",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Point the source URL directly at its final destination instead of chaining through "
                    "intermediate redirects, then verify it now resolves in one hop."
                ),
                "priority": "medium",
            },
        })
    return findings


# ---------------------------------------------------------------------------
# C4 - Raw vs Rendered HTML
# ---------------------------------------------------------------------------


def _c4_raw_vs_rendered(render_comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    js_dependent = []
    for comp in render_comparisons:
        ratio = comp.get("content_difference_ratio", 0.0)
        url = comp.get("url", "")
        raw_len = comp.get("raw_text_length", 0)
        rendered_len = comp.get("rendered_text_length", 0)
        missing_headings = comp.get("missing_headings", [])
        if ratio < RENDER_DIFF_THRESHOLD:
            continue
        if raw_len > 500 and not missing_headings:
            continue
        js_dependent.append({"url": url, "ratio": ratio, "raw_len": raw_len,
                              "rendered_len": rendered_len, "missing_headings": missing_headings})

    if not js_dependent:
        return []

    lines = []
    for ex in js_dependent[:3]:
        pct = int(ex["ratio"] * 100)
        heads = ", ".join(f'"{h}"' for h in ex["missing_headings"][:3]) if ex["missing_headings"] else "none"
        lines.append(
            f"- `{ex['url']}`: {pct}% JS-only (raw: {ex['raw_len']}c, rendered: {ex['rendered_len']}c). "
            f"Headings missing from raw: {heads}."
        )
    evidence = f"{len(js_dependent)} page(s) hide core content behind JavaScript:\n" + "\n".join(lines)

    return [{
        "title": f"{len(js_dependent)} page(s) hide core content behind JavaScript rendering",
        "severity": "high",
        "category": "C4",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Implement SSR or static generation so content is in the initial HTML response. "
                "AI crawlers and many search bots do not execute JavaScript."
            ),
            "priority": "high",
        },
    }]


# ---------------------------------------------------------------------------
# C5 - Machine-Readable Content
# ---------------------------------------------------------------------------


def _c5_machine_readable(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    problem_pages = []
    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        html_data = analysis.get("html", {})
        signals = html_data.get("non_text_content_signals", [])
        is_important = any(kw in url.lower() for kw in _IMPORTANT_PATH_KEYWORDS)
        canvas_signal = next((s for s in signals if s.get("type") == "canvas"), None)
        img_signal = next((s for s in signals if s.get("type") == "image_as_text"), None)
        text_length = html_data.get("text_length", 999)

        if canvas_signal and text_length < 300 and is_important:
            problem_pages.append({"url": url, "detail": f"Canvas primary content; only {text_length} text chars."})
        elif img_signal and is_important:
            count = img_signal.get("count", 0)
            problem_pages.append({"url": url, "detail": f"{count} image(s) may carry important textual data."})

    if not problem_pages:
        return []

    lines = [f"- `{p['url']}`: {p['detail']}" for p in problem_pages[:5]]
    evidence = f"{len(problem_pages)} page(s) have content locked in non-text formats:\n" + "\n".join(lines)

    return [{
        "title": "Important content is locked in non-machine-readable formats (images/canvas)",
        "severity": "medium",
        "category": "C5",
        "evidence": evidence,
        "suggested_action": {
            "summary": "Replace image-based text with HTML text. Add descriptive alt text to informational images.",
            "priority": "medium",
        },
    }]


# ---------------------------------------------------------------------------
# C6 - Structured Data Presence
# ---------------------------------------------------------------------------


def _c6_structured_data_presence(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    missing = []
    for page, analysis in zip(pages, page_analyses):
        status = page.get("status")
        if status and status >= 400:
            # An HTTP error page (4xx/5xx) is not real content -- recommending
            # structured data for it is meaningless; the actual problem is the
            # broken page itself, which C2 already reports (confirmed on a
            # real unseen site: a 404 page was recommended Product/Offer schema).
            continue
        url = page.get("final_url") or page.get("url", "")
        sd = analysis.get("structured_data", {})
        html_data = analysis.get("html", {})
        has_any_sd = bool(sd.get("jsonld") or sd.get("microdata") or sd.get("rdfa"))
        if has_any_sd:
            continue
        suggestion = _heuristic_schema_suggestion(url)
        if suggestion:
            missing.append({"url": url, "suggestion": suggestion})

    if not missing:
        return []

    lines = [f"- `{m['url']}`: {m['suggestion']}" for m in missing[:5]]
    evidence = f"{len(missing)} page(s) missing structured data:\n" + "\n".join(lines)

    return [{
        "title": f"{len(missing)} page(s) missing structured data (JSON-LD/Microdata)",
        "severity": "medium",
        "category": "C6",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Add JSON-LD structured data to key pages. Priority: Product pages -> Product/Offer, "
                "Organization page -> Organization, FAQ pages -> FAQPage, Articles -> Article."
            ),
            "priority": "medium",
        },
    }]


def _heuristic_schema_suggestion(url: str) -> str | None:
    """Suggest a schema type based on URL path keywords.

    Conservative: only suggest when URL clearly indicates a specific content type.
    Does NOT suggest Article schema for pages with 'news' in the domain or path
    when the path looks like a list/index (e.g., /news, /newest, /news?p=2).
    """
    url_lower = url.lower()
    parsed_path = url_lower.split("?")[0].rstrip("/")  # path without query
    # Extract the last path segment to judge page type
    last_segment = parsed_path.split("/")[-1] if "/" in parsed_path else parsed_path

    if any(kw in url_lower for kw in ("product", "shop", "store", "item")):
        # Avoid flagging list/category pages (e.g., /products, /shop)
        if any(url_lower.endswith("/" + kw) or url_lower.endswith("/" + kw + "s")
               for kw in ("product", "products", "shop", "store", "items")):
            return None  # Likely a category/list page, not a product detail
        return "Product/Offer schema recommended"

    if any(kw in url_lower for kw in ("about", "company", "team")):
        return "Organization schema recommended"

    if any(kw in url_lower for kw in ("faq", "help", "support")):
        # Only flag specific FAQ pages, not general support hubs
        if "faq" in last_segment or "faq" in url_lower:
            return "FAQPage schema recommended"
        return None

    if any(kw in url_lower for kw in ("blog", "article", "post")):
        # Only flag individual article/post pages, not list/index pages
        # Heuristic: if the last segment looks like a slug (has dashes or is long), it's an article
        if "-" in last_segment or len(last_segment) > 20:
            return "Article schema recommended"
        return None  # Likely a blog index, not an article

    # Explicitly exclude 'news' keyword: too many false positives on
    # aggregator sites (HN, Reddit) and news homepages which are list pages
    # news.example.com/news, /newest, /news?p=2 etc.

    if "contact" in url_lower:
        return "LocalBusiness or Organization schema recommended"

    return None


# ---------------------------------------------------------------------------
# C7 - Structured Data Consistency
# ---------------------------------------------------------------------------


def _c7_structured_data_consistency(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
    js_heavy_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    inconsistencies = []
    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        if url in js_heavy_urls:
            # Raw HTML is known to be substantially incomplete for this
            # page (see C4) — visible_text extracted from it is not a
            # reliable basis for "structured data doesn't match the page".
            continue
        sd = analysis.get("structured_data", {})
        html_data = analysis.get("html", {})
        visible_text = html_data.get("text", "")
        for item in sd.get("jsonld", []):
            if not item.get("valid") or not item.get("parsed"):
                continue
            try:
                # check_consistency expects (structured_data_dict, visible_content_dict)
                # where visible_content has keys: visible_text, title, h1, prices
                headings_data = html_data.get("headings", {})
                visible_content_dict = {
                    "visible_text": visible_text,
                    "title": analysis.get("metadata", {}).get("title", "") or "",
                    "h1": headings_data.get("h1", []),
                    "prices": [],
                }
                sd_wrapper = {"jsonld": [item]}
                conflicts = check_consistency(sd_wrapper, visible_content_dict)
            except Exception as exc:
                log.debug("check_consistency failed for %s: %s", url, exc)
                continue
            for conflict in (conflicts or []):
                conflict_str = conflict.get("detail", str(conflict)) if isinstance(conflict, dict) else str(conflict)
                inconsistencies.append({"url": url, "conflict": conflict_str})

    if not inconsistencies:
        return []

    high_fields = ("price", "pricecurrency", "availability")
    high_issues = [i for i in inconsistencies if any(f in i["conflict"].lower() for f in high_fields)]
    other_issues = [i for i in inconsistencies if i not in high_issues]
    findings = []

    if high_issues:
        lines = [f"- `{i['url']}`: {i['conflict']}" for i in high_issues[:5]]
        evidence = f"{len(high_issues)} critical SD inconsistency(ies) (price/availability):\n" + "\n".join(lines)
        findings.append({
            "title": "Structured data contradicts visible price or availability information",
            "severity": "high",
            "category": "C7",
            "evidence": evidence,
            "suggested_action": {
                "summary": "Update structured data to exactly match visible page content for price and availability.",
                "priority": "high",
            },
        })

    if other_issues:
        lines = [f"- `{i['url']}`: {i['conflict']}" for i in other_issues[:5]]
        evidence = f"{len(other_issues)} SD inconsistency(ies) (name/description):\n" + "\n".join(lines)
        findings.append({
            "title": "Structured data name or description inconsistencies detected",
            "severity": "medium",
            "category": "C7",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Update the structured data's `name`/`description` fields (or the visible on-page text) "
                    "so the two agree, then verify the values match after re-rendering the page."
                ),
                "priority": "medium",
            },
        })

    return findings


# ---------------------------------------------------------------------------
# C8 - Robots Meta / X-Robots-Tag
# ---------------------------------------------------------------------------


def _c8_robots_meta(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked_pages = []
    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        meta = analysis.get("metadata", {})
        robots_meta = meta.get("robots_meta") or ""
        x_robots = meta.get("x_robots_tag") or ""
        if is_indexing_blocked(robots_meta, x_robots):
            if any(kw in url.lower() for kw in _IMPORTANT_PATH_KEYWORDS) or page.get("depth", 1) == 0:
                directive = robots_meta or x_robots
                blocked_pages.append(f"`{url}` (directive: `{directive}`)")

    if not blocked_pages:
        return []

    evidence = (
        f"{len(blocked_pages)} important page(s) have noindex/none directives:\n"
        + "\n".join(f"- {p}" for p in blocked_pages[:5])
    )
    return [{
        "title": f"{len(blocked_pages)} important page(s) are blocked from indexing via robots meta",
        "severity": "high",
        "category": "C8",
        "evidence": evidence,
        "suggested_action": {
            "summary": "Remove noindex from important public pages. Only noindex legitimately non-indexable pages.",
            "priority": "high",
        },
    }]


# ---------------------------------------------------------------------------
# C9 - Crawlable Internal Links
# ---------------------------------------------------------------------------


def _crawl_coverage_reliable(crawled_count: int, known_count: int) -> bool:
    """Whether the bounded crawl reached enough of the site's known-URL
    universe to draw a confident conclusion from a URL's ABSENCE among
    crawled pages. Below this, "not found among crawled pages" more likely
    means "outside the bounded crawl" than "genuinely missing/broken".
    Shared between C9 (orphan detection) and C10 (canonical-target lookup)
    since both reason from the same kind of absence-of-evidence.
    """
    coverage = crawled_count / known_count if known_count > 0 else 1.0
    return coverage >= 0.25 or known_count <= crawled_count * 2


def _c9_crawlable_links(
    link_graph: dict[str, list[str]],
    all_known_urls: set[str],
    homepage_url: str,
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings = []

    orphans = find_orphan_pages(link_graph, all_known_urls, homepage_url)
    important_orphans = [u for u in orphans if any(kw in u.lower() for kw in _IMPORTANT_PATH_KEYWORDS)]
    # Bounded-crawl reliability guard: only report orphans when we've crawled
    # enough of the site to have meaningful coverage. If we crawled <25% of known
    # URLs, orphan detection is too unreliable (likely linked from uncrawled pages).
    crawled_count = len(link_graph)
    known_count = len(all_known_urls)
    orphan_reliable = _crawl_coverage_reliable(crawled_count, known_count)
    if important_orphans and orphan_reliable:
        lines = [f"- `{u}`" for u in important_orphans[:8]]
        evidence = f"{len(important_orphans)} important page(s) have no inbound links:\n" + "\n".join(lines)
        if len(important_orphans) > 8:
            evidence += f"\n...and {len(important_orphans) - 8} more."
        findings.append({
            "title": f"{len(important_orphans)} important page(s) are orphans (not linked to from any crawled page)",
            "severity": "medium",
            "category": "C9",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Add an inbound link to each page above from the homepage, main navigation, or a "
                    "relevant hub page, then verify the link appears in the page's rendered HTML."
                ),
                "priority": "medium",
            },
        })
    elif important_orphans and not orphan_reliable:
        # Low coverage: note it but don't report as a finding
        log.info("C9 orphan check suppressed: low crawl coverage (%d/%d pages known)",
                 crawled_count, known_count)

    disconnected = find_disconnected_pages(link_graph, homepage_url)
    important_disconnected = [u for u in disconnected if any(kw in u.lower() for kw in _IMPORTANT_PATH_KEYWORDS)]
    if important_disconnected:
        lines = [f"- `{u}`" for u in important_disconnected[:5]]
        evidence = f"{len(important_disconnected)} page(s) unreachable from homepage:\n" + "\n".join(lines)
        findings.append({
            "title": f"{len(important_disconnected)} important page(s) are unreachable from the homepage",
            "severity": "medium",
            "category": "C9",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "These pages have no link path at all from the homepage through any crawled page -- "
                    "add at least one link chain (e.g. via site-wide navigation or a hub/sitemap page) "
                    "connecting them to the rest of the site."
                ),
                "priority": "medium",
            },
        })

    nav_coverage = analyze_nav_coverage(pages, homepage_url)
    if nav_coverage.get("checked"):
        nav_count = nav_coverage.get("nav_link_count", 0)
        total_internal = nav_coverage.get("total_internal_links", 0)
        missing_cats = [cat for cat, present in nav_coverage.get("coverage", {}).items() if not present]
        # Only fire when:
        # 1. We detected actual <nav> links (nav_count > 0) proving we can parse nav, OR
        # 2. There are internal links but none match important categories
        # Do NOT fire when nav_count=0 and total_internal=0 (no navigation detected
        # at all - likely uses non-semantic navigation or single-page site).
        # Require at least 3 missing categories AND either some nav links or many internal links.
        has_parseable_nav = nav_count > 0 or total_internal > 5
        if len(missing_cats) >= 3 and has_parseable_nav and total_internal > 0:
            evidence = (
                f"Homepage navigation ({nav_count} nav link(s), {total_internal} internal link(s)) "
                f"is missing links to these categories: {', '.join(missing_cats)}."
            )
            findings.append({
                "title": "Homepage navigation may be missing links to important content categories",
                "severity": "low",
                "category": "C9",
                "evidence": evidence,
                "suggested_action": {
                    "summary": (
                        f"If this is a commercial site, consider adding navigation links for: "
                        f"{', '.join(missing_cats)}. (Note: this check may not apply to "
                        f"documentation, news, or open-source project sites.)"
                    ),
                    "priority": "low",
                },
            })

    return findings


# ---------------------------------------------------------------------------
# C10 - Canonical Consistency
# ---------------------------------------------------------------------------


def _c10_canonical_consistency(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
    all_known_urls: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    problems = []

    # Handle /index.html equivalence:
    # /path/ and /path/index.html are the same page on most servers.
    # Canonicaling /3/ -> /3/index.html is a valid and common pattern.
    def _strip_index(u: str) -> str:
        if u.endswith("/index.html") or u.endswith("/index.htm"):
            return u.rsplit("/", 1)[0] + "/"
        return u

    # Expand each crawled page's normalized URL into every /index.html-
    # equivalent form (same equivalence _strip_index defines below for
    # self-referencing canonicals), so a canonical pointing at ANOTHER
    # already-crawled page's /index.html-equivalent form is recognized too,
    # not just a canonical pointing back at its own page.
    page_urls: set[str] = set()
    for p in pages:
        raw = normalize_url(p.get("final_url") or p.get("url", ""))
        stripped = _strip_index(raw)
        page_urls.add(raw)
        page_urls.add(raw.rstrip("/") + "/")
        page_urls.add(stripped)
        page_urls.add(stripped.rstrip("/") + "/")

    # Bounded-crawl reliability guard (same principle as C9's orphan check):
    # a same-domain canonical target simply not being among the ~15 crawled
    # pages does not mean it's broken -- it may just be outside the bounded
    # crawl (e.g. a locale/paginated variant). Only trust that absence when
    # the crawl reached enough of the site's known-URL universe. Genuine
    # cross-domain canonicals are unaffected -- that signal doesn't depend
    # on crawl coverage.
    coverage_reliable = _crawl_coverage_reliable(len(pages), len(all_known_urls))

    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        normalized_url = normalize_url(url)
        meta = analysis.get("metadata", {})
        canonical = meta.get("canonical")
        if not canonical:
            continue
        # Canonical hrefs are frequently relative (e.g. "/privacy?lang=en").
        # Resolve against the page's own URL before any comparison -- a
        # relative href is same-domain by definition and must never be
        # mistaken for a cross-domain canonical.
        resolved_canonical = urljoin(url, canonical)
        normalized_canonical = normalize_url(resolved_canonical)
        # Direct match: self-referencing canonical, no issue
        if normalized_canonical == normalized_url:
            continue
        # Handle /index.html equivalence against the current page itself:
        # /path/ and /path/index.html are the same page on most servers.
        # Canonicaling /3/ -> /3/index.html is a valid and common pattern.
        if _strip_index(normalized_canonical) == _strip_index(normalized_url):
            continue
        if _strip_index(normalized_canonical) == normalized_url.rstrip("/") + "/":
            continue
        if normalized_canonical == _strip_index(normalized_url):
            continue

        # Membership check against ALL crawled pages: page_urls already
        # contains every /index.html-equivalent form of every crawled page
        # (see above), so also check the canonical's own stripped form here
        # -- this recognizes a canonical pointing at another already-crawled
        # page via an /index.html-equivalent alias, not just a self-reference.
        if normalized_canonical not in page_urls and _strip_index(normalized_canonical) not in page_urls:
            canonical_domain = urlparse(resolved_canonical).netloc.lower()
            current_domain = urlparse(url).netloc.lower()
            if canonical_domain != current_domain:
                problems.append({"url": url, "detail": f"Cross-domain canonical: `{resolved_canonical}`"})
            elif coverage_reliable:
                problems.append({"url": url, "detail": f"Canonical `{resolved_canonical}` not found in crawled pages."})
            else:
                log.info("C10 same-domain canonical-target check suppressed for %s: low crawl coverage "
                         "(%d pages crawled / %d known)", url, len(pages), len(all_known_urls))

    if not problems:
        return []

    lines = [f"- `{p['url']}`: {p['detail']}" for p in problems[:5]]
    evidence = f"{len(problems)} page(s) with problematic canonicals:\n" + "\n".join(lines)

    return [{
        "title": f"{len(problems)} page(s) have suspicious canonical tag configurations",
        "severity": "medium",
        "category": "C10",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Update the `<link rel=\"canonical\">` element on each affected page to point to that "
                "page's own definitive, indexable URL (self-referencing if this page is canonical) instead "
                "of the current target, then verify the rendered HTML exposes the corrected canonical and "
                "that it resolves with HTTP 200."
            ),
            "priority": "medium",
        },
    }]


# ---------------------------------------------------------------------------
# C11 - Page Title / Metadata
# ---------------------------------------------------------------------------


def _c11_page_title_metadata(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bad_titles = []
    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        depth = page.get("depth", 1)
        meta = analysis.get("metadata", {})
        title = meta.get("title")
        is_important = depth == 0 or any(kw in url.lower() for kw in _IMPORTANT_PATH_KEYWORDS)
        if not is_important:
            continue
        assessment = assess_title_quality(title)
        if assessment.get("quality") in ("missing", "empty", "generic"):
            bad_titles.append({"url": url, "quality": assessment["quality"], "reason": assessment.get("reason", "")})

    if not bad_titles:
        return []

    lines = [f"- `{b['url']}`: {b['reason']}" for b in bad_titles[:6]]
    evidence = f"{len(bad_titles)} important page(s) have missing or generic titles:\n" + "\n".join(lines)
    severity = "high" if any(b["quality"] == "missing" for b in bad_titles) else "medium"

    return [{
        "title": f"{len(bad_titles)} important page(s) have missing or meaningless page titles",
        "severity": severity,
        "category": "C11",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Write descriptive unique <title> tags for important pages (30-60 chars). "
                "Include brand name and specific page topic."
            ),
            "priority": severity,
        },
    }]


# ---------------------------------------------------------------------------
# C12 - Heading / Document Structure
# ---------------------------------------------------------------------------


def _c12_heading_structure(
    pages: list[dict[str, Any]],
    page_analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    missing_h1 = []
    multi_h1 = []

    for page, analysis in zip(pages, page_analyses):
        url = page.get("final_url") or page.get("url", "")
        depth = page.get("depth", 1)
        html_data = analysis.get("html", {})
        headings = html_data.get("headings", {})
        text_length = html_data.get("text_length", 0)
        is_important = depth == 0 or any(kw in url.lower() for kw in _IMPORTANT_PATH_KEYWORDS)
        if not is_important or text_length < 200:
            continue

        h1s = headings.get("h1", [])
        if not h1s:
            missing_h1.append({"url": url, "detail": "No H1 heading found."})
        elif len(h1s) > 1:
            multi_h1.append({"url": url, "detail": f"{len(h1s)} H1s: {', '.join(repr(h) for h in h1s[:3])}"})

    findings = []
    if missing_h1:
        lines = [f"- `{p['url']}`: {p['detail']}" for p in missing_h1[:5]]
        evidence = f"{len(missing_h1)} important page(s) missing an H1:\n" + "\n".join(lines)
        findings.append({
            "title": f"{len(missing_h1)} important page(s) are missing an H1 heading",
            "severity": "medium",
            "category": "C12",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Add a single `<h1>` heading to each affected page describing that page's specific "
                    "topic, then verify it renders in the page's HTML."
                ),
                "priority": "medium",
            },
        })
    if multi_h1:
        lines = [f"- `{p['url']}`: {p['detail']}" for p in multi_h1[:5]]
        evidence = f"{len(multi_h1)} page(s) with multiple H1 headings:\n" + "\n".join(lines)
        findings.append({
            "title": f"{len(multi_h1)} page(s) have multiple H1 headings (ambiguous topic)",
            "severity": "low",
            "category": "C12",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Keep only the most representative heading as the page's `<h1>` and demote the others "
                    "to `<h2>`/`<h3>`, then verify each page renders exactly one H1."
                ),
                "priority": "low",
            },
        })

    return findings


# ---------------------------------------------------------------------------
# Proactive opportunities (not defects) — evidence-gated, non-overlapping
# with C1-C12. Kept separate from findings: these are enhancement
# suggestions, never a claim that something is broken.
# ---------------------------------------------------------------------------


def identify_proactive_opportunities(
    crawl_result: dict[str, Any],
    robots_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Identify sitemap/indexability opportunities that are not defects.

    Two mutually-exclusive, evidence-gated checks, both reusing sitemap data
    already collected by the shared crawl (no new network calls):

    - A sitemap exists (confirmed at the default /sitemap.xml location) but
      robots.txt doesn't declare a Sitemap: directive for it.
    - No sitemap was found via either path at all.

    Neither overlaps C1 (permission), C8 (indexing directives), C9
    (crawlable links), or C10 (canonical) — none of those check sitemap
    presence/declaration itself.
    """
    robots_sitemap_urls = (robots_data or {}).get("sitemap_urls") or []
    crawl_sitemap_urls = crawl_result.get("sitemap_urls") or []
    robots_exists = bool((robots_data or {}).get("exists"))

    opportunities: list[dict[str, Any]] = []

    if robots_exists and not robots_sitemap_urls and crawl_sitemap_urls:
        opportunities.append({
            "title": "Sitemap exists but isn't referenced from robots.txt",
            "evidence": (
                f"A sitemap was found at the default location ({len(crawl_sitemap_urls)} URL(s) listed), "
                "but robots.txt does not declare a `Sitemap:` directive pointing to it."
            ),
            "suggested_action": {
                "summary": "Add a `Sitemap:` line to robots.txt referencing your existing sitemap, so crawlers can find it without guessing the URL.",
                "priority": "low",
            },
        })
    elif not robots_sitemap_urls and not crawl_sitemap_urls:
        opportunities.append({
            "title": "No sitemap was found",
            "evidence": (
                "No `Sitemap:` directive was found in robots.txt, and no sitemap was found at the "
                "default /sitemap.xml location."
            ),
            "suggested_action": {
                "summary": "Add a sitemap.xml (and reference it from robots.txt) so crawlers can discover your site's pages systematically rather than relying only on following links.",
                "priority": "low",
            },
        })

    return opportunities