"""
Audit Runner - Main F1-F5 detector engine for the freshness-corroboration skill.

Orchestrates identity, freshness, fact-consistency, and corroboration
detectors against already-crawled page data (as produced by the
crawl-render-audit skill) and returns a structured list of findings.

Detector coverage:
    F1 - Brand identity consistency
    F2 - Entity ambiguity risk
    F3 - Internal fact consistency
    F4 - Freshness / staleness of time-sensitive content
    F5 - External corroboration (bounded, provider-neutral)

F6 (important claim detection) is internal support logic feeding F5, not a
finding-producing detector in its own right.
"""

from __future__ import annotations

import logging
from typing import Any

from .identity_analysis import (
    assess_entity_ambiguity,
    build_site_identity_profile,
    compare_identity,
    extract_identity_signals,
)
from .freshness_analysis import analyze_freshness
from .fact_consistency import extract_facts, find_contradictions
from .corroboration import assess_corroboration_confidence, corroborate_claims, verify_same_as_links

log = logging.getLogger(__name__)

_STALENESS_SEVERITY = {
    "expired_offer_still_displayed": "high",
    "past_tense_as_present": "medium",
    "date_order_inversion": "low",
}

_STALENESS_ACTION = {
    "expired_offer_still_displayed": (
        "Remove or update the expired offer/date reference identified above so it no longer displays as "
        "current, then add a `dateModified` value reflecting the change."
    ),
    "past_tense_as_present": (
        "Update or remove the reference to the past year/event identified above so the content no longer "
        "reads as upcoming, then add a `dateModified` value reflecting the update."
    ),
    "date_order_inversion": (
        "Correct the page's `datePublished`/`dateModified` values so `dateModified` is not earlier than "
        "`datePublished`."
    ),
}
_DEFAULT_STALENESS_ACTION = (
    "Update or remove the outdated time-sensitive content identified above and add a `dateModified` value "
    "reflecting the change."
)


def run_freshness_audit(
    crawl_result: dict[str, Any],
    external_sources: list[dict[str, Any]] | None = None,
    max_sameas_links: int = 5,
) -> list[dict[str, Any]]:
    """Run all F1-F5 detectors and return a list of findings.

    Args:
        crawl_result: Output from crawl.bounded_crawl() with a 'pages' key
            (as produced by the crawl-render-audit skill). Reused as-is —
            this skill does not perform its own crawling.
        external_sources: Optional pre-judged external source verdicts for
            Tier B corroboration (see corroboration.py docstring). Omit to
            run Tier A (sameAs health) corroboration only.
        max_sameas_links: Bound on external HTTP requests for F5 Tier A.

    Returns:
        List of finding dicts with title, severity, category, evidence,
        and suggested_action.
    """
    pages: list[dict[str, Any]] = crawl_result.get("pages", [])
    if not pages:
        return []

    findings: list[dict[str, Any]] = []

    identity_signals = []
    facts_by_page = []
    freshness_by_page = []
    for page in pages:
        html = page.get("body", "") or ""
        url = page.get("final_url") or page.get("url", "")
        depth = page.get("depth", 1)
        try:
            sig = extract_identity_signals(html, url)
            sig["depth"] = depth
            identity_signals.append(sig)
        except Exception as exc:
            log.warning("identity_analysis failed for %s: %s", url, exc)
        try:
            facts_by_page.append(extract_facts(html, url, depth=depth))
        except Exception as exc:
            log.warning("fact_consistency failed for %s: %s", url, exc)
        try:
            freshness_by_page.append(analyze_freshness(html, url))
        except Exception as exc:
            log.warning("freshness_analysis failed for %s: %s", url, exc)

    findings += _f1_identity_consistency(identity_signals)
    findings += _f2_entity_ambiguity(identity_signals)
    findings += _f3_fact_consistency(facts_by_page)
    findings += _f4_freshness(freshness_by_page)
    findings += _f5_corroboration(identity_signals, external_sources, max_sameas_links)

    return findings


def _f1_identity_consistency(identity_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not identity_signals:
        return []
    comparison = compare_identity(identity_signals)
    contradictions = comparison.get("contradictions", [])
    if not contradictions:
        return []

    lines = [f"- {c['detail']}" for c in contradictions[:5]]
    evidence = f"{len(contradictions)} brand identity contradiction(s) found:\n" + "\n".join(lines)

    return [{
        "title": f"{len(contradictions)} brand identity contradiction(s) across pages",
        "severity": "high",
        "category": "F1",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Reconcile the organization name used in visible branding with the name declared "
                "in structured data. Use `alternateName` for legitimate brand-name variants."
            ),
            "priority": "high",
        },
    }]


def _f2_entity_ambiguity(identity_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not identity_signals:
        return []
    profile = build_site_identity_profile(identity_signals)
    assessment = assess_entity_ambiguity(profile)
    risk = assessment.get("risk_level")
    if risk not in ("medium", "high"):
        return []

    concerns = assessment.get("concerns", [])
    evidence = " ".join(concerns) if concerns else f"Entity ambiguity risk assessed as {risk}."

    return [{
        "title": "Website provides limited entity-distinguishing information (ambiguity risk)",
        "severity": "medium" if risk == "medium" else "high",
        "category": "F2",
        "evidence": evidence,
        "suggested_action": {
            "summary": (
                "Add the distinguishing identity signals noted above (e.g. sameAs links, an organization "
                "description, a logo, or a location/address) to the site's Organization schema, then "
                "verify the added fields appear in the page's structured data."
            ),
            "priority": "medium" if risk == "medium" else "high",
        },
    }]


def _f3_fact_consistency(facts_by_page: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(facts_by_page) < 2:
        return []
    contradictions = find_contradictions(facts_by_page)
    if not contradictions:
        return []

    findings = []
    by_field: dict[str, list[dict[str, Any]]] = {}
    for c in contradictions:
        by_field.setdefault(c["field"], []).append(c)

    for field, items in by_field.items():
        severity = items[0].get("severity_hint", "medium")
        lines = [f"- {c['detail']}" for c in items[:5]]
        evidence = f"{len(items)} {field} contradiction(s) found across pages:\n" + "\n".join(lines)
        findings.append({
            "title": f"Inconsistent {field} information across pages",
            "severity": severity,
            "category": "F3",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    f"Update the pages listed above so they state the same {field} value, choosing the "
                    f"correct one as the single source of truth, then verify the {field} matches on every "
                    f"affected page."
                ),
                "priority": severity,
            },
        })
    return findings


def _f4_freshness(freshness_by_page: list[dict[str, Any]]) -> list[dict[str, Any]]:
    all_signals: list[tuple[str, dict[str, Any]]] = []
    for page_fresh in freshness_by_page:
        url = page_fresh.get("url", "")
        for sig in page_fresh.get("staleness_signals", []):
            all_signals.append((url, sig))

    if not all_signals:
        return []

    findings = []
    by_type: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for url, sig in all_signals:
        by_type.setdefault(sig["type"], []).append((url, sig))

    for sig_type, items in by_type.items():
        severity = _STALENESS_SEVERITY.get(sig_type, "medium")
        lines = [f"- `{url}`: {sig['detail']} (\"{sig['evidence_text']}\")" for url, sig in items[:5]]
        evidence = f"{len(items)} page(s) show evidence of stale time-sensitive content:\n" + "\n".join(lines)
        findings.append({
            "title": f"Time-sensitive content appears stale ({sig_type.replace('_', ' ')})",
            "severity": severity,
            "category": "F4",
            "evidence": evidence,
            "suggested_action": {
                "summary": _STALENESS_ACTION.get(sig_type, _DEFAULT_STALENESS_ACTION),
                "priority": severity,
            },
        })
    return findings


def _f5_corroboration(
    identity_signals: list[dict[str, Any]],
    external_sources: list[dict[str, Any]] | None,
    max_sameas_links: int,
) -> list[dict[str, Any]]:
    if not identity_signals:
        return []
    profile = build_site_identity_profile(identity_signals)
    same_as = profile.get("same_as", [])

    same_as_results = (
        verify_same_as_links(same_as, expected_name=profile.get("name", ""), max_links=max_sameas_links)
        if same_as else []
    )

    claims = []
    if profile.get("name"):
        claims.append({"claim": "organization_identity", "value": profile["name"], "category": "identity"})

    corrob_results = corroborate_claims(claims, same_as_results=same_as_results, external_sources=external_sources)
    # assess_corroboration_confidence() is available to callers/orchestrator
    # for an overall summary; it is intentionally not itself turned into a
    # finding (an "unconfirmed"/"not_attempted" confidence level is not a
    # defect — see corroboration.py docstring).
    _ = assess_corroboration_confidence(corrob_results)

    findings = []
    broken_refs = [r for r in corrob_results if r.get("type") == "reference_check" and r.get("status") in ("broken", "unrelated")]
    if broken_refs:
        lines = [f"- `{r['source_url']}`: {r['detail']}" for r in broken_refs[:5]]
        evidence = f"{len(broken_refs)} sameAs reference(s) appear broken or unrelated:\n" + "\n".join(lines)
        findings.append({
            "title": f"{len(broken_refs)} sameAs reference(s) are broken or no longer relevant",
            "severity": "medium",
            "category": "F5",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Update or remove the sameAs link(s) identified above so each one resolves to this "
                    "organization's own official profile, then verify the link is reachable and displays "
                    "the expected organization name."
                ),
                "priority": "medium",
            },
        })

    contradicted = [r for r in corrob_results if r.get("type") == "claim_check" and r.get("status") == "contradicted"]
    if contradicted:
        lines = [f"- {r['claim']}: {r['detail']} (source: {r.get('source_url', 'n/a')}, tier {r.get('tier')})" for r in contradicted[:5]]
        evidence = f"{len(contradicted)} claim(s) contradicted by an independent source:\n" + "\n".join(lines)
        severity = "high" if any(r.get("category") == "identity" for r in contradicted) else "medium"
        findings.append({
            "title": f"{len(contradicted)} claim(s) contradicted by external source(s)",
            "severity": severity,
            "category": "F5",
            "evidence": evidence,
            "suggested_action": {
                "summary": (
                    "Compare the specific claim identified above against the independent source cited in "
                    "the evidence, then correct whichever record is inaccurate -- the site's own content, "
                    "or (if within your control) request a correction from the external source."
                ),
                "priority": severity,
            },
        })

    return findings


# ---------------------------------------------------------------------------
# Proactive opportunities (not defects) — evidence-gated, non-overlapping
# with F1-F5. Kept separate from findings: these are enhancement
# suggestions, never a claim that something is broken.
# ---------------------------------------------------------------------------


def identify_proactive_opportunities(crawl_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Identify freshness/identity enhancement opportunities that are not
    defects. No new network calls or crawling — reuses the same per-page
    analysis (identity signals, freshness signals) the F1-F5 detectors
    already compute.

    P3 (sameAs corroboration): only fires when a genuine Organization schema
    name is declared and sameAs is entirely empty, AND only when F2 would
    NOT also be flagging entity ambiguity for this site (checked directly
    via assess_entity_ambiguity, not by guessing) — otherwise F2's own
    suggested_action already covers the same ground and this would be a
    redundant repeat of the same advice.

    P4 (freshness metadata): only fires for a page with at least two
    distinct HIGH-sensitivity time indicators (a single incidental keyword
    is not "genuinely identifiable" time-sensitive content), no structured
    dateModified/datePublished at all, and no staleness_signals already
    present for that page (F4 already covers pages with actual staleness
    evidence; P4 is strictly about pages where dates are simply absent).
    """
    pages: list[dict[str, Any]] = crawl_result.get("pages", [])
    if not pages:
        return []

    opportunities: list[dict[str, Any]] = []

    # --- P3: sameAs corroboration opportunity ---
    identity_signals = []
    for page in pages:
        html = page.get("body", "") or ""
        url = page.get("final_url") or page.get("url", "")
        try:
            sig = extract_identity_signals(html, url)
            sig["depth"] = page.get("depth", 1)
            identity_signals.append(sig)
        except Exception as exc:
            log.warning("identity_analysis failed for %s: %s", url, exc)

    if identity_signals:
        profile = build_site_identity_profile(identity_signals)
        if profile.get("name_source") == "schema" and not profile.get("same_as"):
            ambiguity = assess_entity_ambiguity(profile)
            if ambiguity.get("risk_level") not in ("medium", "high"):
                opportunities.append({
                    "title": "Organization identity has no sameAs corroboration links",
                    "evidence": (
                        f"An Organization schema declares the name '{profile['name']}', but no `sameAs` "
                        "links are present anywhere on the crawled pages."
                    ),
                    "suggested_action": {
                        "summary": (
                            "Where genuine, verifiable external profiles for this organization exist "
                            "(e.g. an official social media account, a verified directory listing, or a "
                            "Wikipedia article specifically about this organization), link them via "
                            "`sameAs` so AI systems can corroborate the declared identity. Do not add a "
                            "`sameAs` link unless it demonstrably represents this exact organization."
                        ),
                        "priority": "low",
                    },
                })

    # --- P4: freshness metadata opportunity ---
    p4_pages = []
    for page in pages:
        html = page.get("body", "") or ""
        url = page.get("final_url") or page.get("url", "")
        try:
            fresh = analyze_freshness(html, url)
        except Exception as exc:
            log.warning("freshness_analysis failed for %s: %s", url, exc)
            continue

        if fresh.get("staleness_signals"):
            continue  # already covered by F4 for this page

        high_categories = {
            c["category"] for c in fresh.get("time_sensitive_content", [])
            if c.get("sensitivity") == "high"
        }
        if len(high_categories) < 2:
            continue  # not genuinely/substantively time-sensitive, just an incidental keyword

        has_structured_date = any(
            d.get("type") in ("datePublished", "dateModified") for d in fresh.get("dates_found", [])
        )
        if has_structured_date:
            continue

        p4_pages.append({"url": url, "categories": sorted(high_categories)})

    if p4_pages:
        lines = [f"- `{p['url']}`: mentions {', '.join(p['categories'])}" for p in p4_pages[:5]]
        opportunities.append({
            "title": f"{len(p4_pages)} page(s) with time-sensitive content have no freshness metadata",
            "evidence": (
                f"{len(p4_pages)} page(s) contain multiple time-sensitive indicators but no "
                f"`dateModified`/`datePublished`:\n" + "\n".join(lines)
            ),
            "suggested_action": {
                "summary": (
                    "If this content is actively maintained, adding an explicit `dateModified` (or "
                    "`datePublished`) lets AI systems verify its freshness directly rather than needing "
                    "to infer it."
                ),
                "priority": "low",
            },
        })

    return opportunities
