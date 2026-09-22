"""
Corroboration — External source lookup and confidence assessment.

Where practical, identifies independent sources that support or contradict
key claims made on the website. Uses only publicly available, non-proprietary
methods.

Design (bounded, provider-neutral, read-only):

Tier A — sameAs reference health (fully automated, no search required):
    A bounded number of the organization's own declared sameAs links
    (LinkedIn, Wikipedia, etc.) are fetched read-only to confirm they are
    reachable and plausibly still about the same organization. This never
    requires a search API or credentials.

Tier B — agent-supplied external source verdicts (optional):
    Detecting semantic contradiction in arbitrary free text is not something
    this deterministic module attempts — that judgment belongs to whichever
    agent gathered the source (e.g. a web search performed by the
    orchestrating agent). This module only accepts an ALREADY-JUDGED verdict
    per source (`contradicts_claim: bool`, `tier: 1|2|3`) and aggregates it.
    If no external sources are supplied, Tier B is simply skipped — absence
    of corroboration is never itself treated as a finding.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

_KNOWN_SAMEAS_HOSTS = (
    "linkedin.com", "wikipedia.org", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "github.com", "youtube.com", "crunchbase.com",
    "wikidata.org", "pinterest.com", "tiktok.com",
)

_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|group|"
    r"gmbh|plc|srl|pvt|pty|llp|lp)\b\.?",
    re.IGNORECASE,
)


def _is_known_platform(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith(f".{h}") for h in _KNOWN_SAMEAS_HOSTS)


def _loose_name_in_text(name: str, text_lower: str) -> bool:
    if not name:
        return True  # nothing to check against; don't manufacture a mismatch
    normalized = _CORPORATE_SUFFIX_RE.sub("", name.lower())
    normalized = re.sub(r"[^\w\s]", "", normalized).strip()
    if not normalized:
        return True
    # Require the most distinctive token (first word) to appear.
    first_token = normalized.split(" ")[0]
    return len(first_token) > 2 and first_token in text_lower


def verify_same_as_links(
    same_as_urls: list[str],
    expected_name: str = "",
    max_links: int = 5,
    timeout: float = 8.0,
) -> list[dict[str, Any]]:
    """Bounded, read-only check that declared sameAs links are reachable and
    plausibly still about the same organization.

    Distinguishes a link that is genuinely broken (404/410/connection
    failure) from one that could not be verified because the third-party
    platform itself blocks non-browser HTTP clients — very common for
    social platforms (confirmed on a real unseen site in Stage 7, where
    Facebook/Instagram/YouTube all returned non-content responses to a
    plain HTTP client despite the links being genuinely valid). A blocked
    or too-small response is marked `likely_blocked`, distinct from
    `reachable`, so callers never have to treat "we couldn't check" the
    same as "this is wrong".

    Args:
        same_as_urls: sameAs URLs declared in the site's own structured data.
        expected_name: The organization's declared name, used for a loose
            containment check against the fetched page (not a strict proof).
        max_links: Hard cap on number of external requests made.
        timeout: Per-request timeout in seconds.

    Returns:
        List of per-link verification results.
    """
    results: list[dict[str, Any]] = []
    for url in list(dict.fromkeys(same_as_urls))[:max_links]:
        entry: dict[str, Any] = {
            "url": url,
            "reachable": False,
            "status": None,
            "known_platform": _is_known_platform(url),
            "name_found": None,
            "likely_blocked": False,
            "error": None,
        }
        try:
            resp = httpx.get(
                url, timeout=timeout, follow_redirects=True,
                headers={"User-Agent": "BrandAIReadinessAudit/1.0"},
            )
            entry["status"] = resp.status_code
            entry["reachable"] = resp.status_code < 400
            if resp.status_code in (401, 403, 429, 999):
                # Status codes commonly used for bot-detection/rate-limiting
                # rather than "this resource does not exist".
                entry["likely_blocked"] = True
            elif entry["reachable"]:
                # A suspiciously small response (e.g. a login-wall or
                # generic interstitial) cannot be confidently read as "the
                # real profile, and it doesn't mention the name" — that
                # requires an actual substantial page.
                if len(resp.text) < 2000:
                    entry["likely_blocked"] = True
                elif expected_name:
                    entry["name_found"] = _loose_name_in_text(expected_name, resp.text[:20000].lower())
        except httpx.TimeoutException:
            entry["error"] = "timeout"
        except httpx.HTTPError as exc:
            entry["error"] = str(exc)
        results.append(entry)
    return results


def corroborate_claims(
    claims: list[dict[str, Any]],
    same_as_results: list[dict[str, Any]] | None = None,
    external_sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attempt to corroborate key claims from external sources.

    Args:
        claims: List of claim dicts with 'claim', 'value', 'category'.
        same_as_results: Output of verify_same_as_links() (Tier A), or None.
        external_sources: Optional list of externally-judged source verdicts,
            each: {"claim": str, "source_url": str, "tier": 1|2|3,
            "contradicts_claim": bool, "detail": str}. The semantic judgment
            of whether a source contradicts a claim is made by whoever
            supplies this list (e.g. the orchestrating agent), not by this
            function. If omitted, only Tier A (sameAs health) is assessed.

    Returns:
        List of corroboration result entries. Absence of external data
        produces "not_attempted" entries, never a fabricated finding.
    """
    results: list[dict[str, Any]] = []
    same_as_results = same_as_results or []
    external_sources = external_sources or []

    for r in same_as_results:
        if r.get("likely_blocked"):
            results.append({
                "type": "reference_check",
                "source_url": r["url"],
                "status": "unverifiable",
                "detail": (
                    f"sameAs reference returned a response (status={r.get('status')}) consistent with "
                    "third-party bot-blocking or a login wall, not necessarily a broken link — could not verify."
                ),
            })
        elif not r.get("reachable"):
            results.append({
                "type": "reference_check",
                "source_url": r["url"],
                "status": "broken",
                "detail": f"sameAs reference is unreachable ({r.get('error') or r.get('status')}).",
            })
        elif r.get("known_platform") and r.get("name_found") is False:
            results.append({
                "type": "reference_check",
                "source_url": r["url"],
                "status": "unrelated",
                "detail": "sameAs reference is reachable but does not appear to reference the organization's name.",
            })
        else:
            results.append({
                "type": "reference_check",
                "source_url": r["url"],
                "status": "ok",
                "detail": "sameAs reference is reachable.",
            })

    for claim in claims:
        claim_id = claim.get("claim")
        category = claim.get("category", "general")
        matching = [s for s in external_sources if s.get("claim") == claim_id]

        if not matching:
            results.append({
                "type": "claim_check", "claim": claim_id, "category": category,
                "status": "not_attempted",
                "detail": "No external source data supplied for this claim.",
            })
            continue

        # Only tier 1/2 contradictions are treated as definitive; a lone
        # tier-3 (low-quality/unverified) source is never enough to flag a
        # contradiction on its own.
        contradicting = [s for s in matching if s.get("contradicts_claim") and s.get("tier", 3) <= 2]
        confirming = [s for s in matching if not s.get("contradicts_claim")]

        if contradicting:
            best = min(contradicting, key=lambda s: s.get("tier", 3))
            results.append({
                "type": "claim_check", "claim": claim_id, "category": category,
                "status": "contradicted",
                "tier": best.get("tier"),
                "source_url": best.get("source_url"),
                "detail": best.get("detail") or f"External source contradicts claim: {claim_id}",
            })
        elif confirming:
            results.append({
                "type": "claim_check", "claim": claim_id, "category": category,
                "status": "corroborated",
                "sources": [s.get("source_url") for s in confirming],
            })
        else:
            results.append({
                "type": "claim_check", "claim": claim_id, "category": category,
                "status": "uncertain",
                "detail": "Only low-confidence (tier 3) contradicting signals found; not treated as definitive.",
            })

    return results


def assess_corroboration_confidence(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess overall corroboration confidence.

    Returns:
        Confidence assessment with tier breakdown. "not_attempted" when no
        data exists at all — this is explicitly NOT the same as "contradicted",
        and is never itself reported as a finding.
    """
    tier_counts = {1: 0, 2: 0, 3: 0}
    contradictions = 0
    corroborated = 0
    broken_or_unrelated = 0
    unverifiable = 0

    for r in results:
        if r.get("type") == "reference_check":
            if r.get("status") in ("broken", "unrelated"):
                broken_or_unrelated += 1
            elif r.get("status") == "unverifiable":
                unverifiable += 1
        if r.get("type") == "claim_check":
            if r.get("status") == "contradicted":
                contradictions += 1
                tier = r.get("tier")
                if tier in tier_counts:
                    tier_counts[tier] += 1
            elif r.get("status") == "corroborated":
                corroborated += 1

    if not results:
        overall = "not_attempted"
    elif contradictions > 0:
        overall = "contradicted"
    elif corroborated > 0:
        overall = "corroborated"
    else:
        overall = "unconfirmed"

    return {
        "overall_confidence": overall,
        "tier_1_sources": tier_counts[1],
        "tier_2_sources": tier_counts[2],
        "tier_3_sources": tier_counts[3],
        "contradictions_found": contradictions,
        "broken_or_unrelated_references": broken_or_unrelated,
        "unverifiable_references": unverifiable,
    }
