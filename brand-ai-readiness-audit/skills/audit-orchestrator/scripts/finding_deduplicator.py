"""
Finding Deduplicator — Merges overlapping findings from different specialist skills.

Identifies findings that describe the same root cause and merges them,
keeping the strongest evidence and most appropriate severity.

Design note (Option B — text-based URL extraction):

Specialist findings (crawl-render-audit, freshness-corroboration,
engagement-audit) do not carry a structured "url" field — each finding's
evidence string consistently references affected page(s) as backtick-quoted
URLs, e.g. "- `https://site/page`: ...". This module extracts those URLs
with a regex rather than relying on a structured field that does not exist.

Limitation: this is inherently best-effort. It depends on the existing
evidence-formatting convention (backtick-quoted absolute URLs) holding across
all three specialist skills, and cannot recover a URL from evidence text that
doesn't follow that convention. When no URL can be extracted from a finding,
this module deliberately does NOT fall back to grouping by category alone —
doing so would risk merging unrelated findings that merely share a detector
category across an entire site. A future, more robust design would have each
specialist finding carry a structured "urls" field; that is out of scope for
Stage 5 and would require changes to the (already signed-off) specialist
skills.

Two findings are only merged when BOTH of the following hold:
  1. They share the same detector `category` (e.g. "C6", "F3", "E9") — since
     categories are already namespaced per detector, this alone prevents any
     cross-detector merging (no special-casing like "E7+E9" is needed or used).
  2. Their extracted URL sets overlap (share at least one URL).
A pure exact-duplicate short-circuit (identical title + category + evidence)
also collapses immediately, independent of URL extraction, to guard against
accidental double-invocation of the same detector.
"""

from __future__ import annotations

import re
from typing import Any

_URL_RE = re.compile(r"`(https?://[^`\s]+)`")

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _extract_urls(evidence: str) -> set[str]:
    """Extract backtick-quoted URLs from a finding's evidence text.

    Best-effort only — see module docstring for the documented limitation.
    """
    if not evidence:
        return set()
    return set(_URL_RE.findall(evidence))


def _severity_of(finding: dict[str, Any]) -> int:
    return _SEVERITY_RANK.get(str(finding.get("severity", "medium")).lower(), 2)


def _similarity_key(finding: dict[str, Any]) -> str:
    """Generate a grouping key for a finding based on URL and category."""
    urls = _extract_urls(finding.get("evidence", ""))
    category = finding.get("category", "")
    return f"{category}::{'|'.join(sorted(urls))}"


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge a group of same-root-cause findings into one.

    Keeps the highest-severity title/suggested_action, and combines any
    distinct evidence text from the group.
    """
    if len(group) == 1:
        return group[0]

    base = min(group, key=_severity_of)  # lowest rank number = highest severity
    other_evidence = [
        f["evidence"] for f in group
        if f is not base and f.get("evidence") and f["evidence"] != base.get("evidence")
    ]

    merged = dict(base)
    if other_evidence:
        combined = "\n---\n".join([base.get("evidence", "")] + other_evidence)
        merged["evidence"] = combined + f"\n(Merged from {len(group)} similar findings.)"
    return merged


def deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate or overlapping findings.

    Deduplication strategy:
    1. Collapse exact duplicates (identical title + category + evidence).
    2. Among the remainder, group findings that share both a detector
       category and at least one overlapping URL extracted from their
       evidence text; merge each such group into one finding.
    3. Findings from which no URL could be extracted are never merged with
       anything (conservative fallback — see module docstring).

    Args:
        findings: List of raw finding dicts from specialist skills.

    Returns:
        Deduplicated list of findings.
    """
    if not findings:
        return []

    # Step 1: exact-duplicate collapse.
    seen_exact: set[tuple[str, str, str]] = set()
    exact_deduped: list[dict[str, Any]] = []
    for f in findings:
        key = (f.get("title", ""), f.get("category", ""), f.get("evidence", ""))
        if key in seen_exact:
            continue
        seen_exact.add(key)
        exact_deduped.append(f)

    # Step 2: group by category + overlapping extracted URLs.
    # Findings with no extractable URL are never grouped with anything.
    groups: list[list[dict[str, Any]]] = []
    group_urls: list[set[str]] = []
    group_categories: list[str] = []

    for f in exact_deduped:
        urls = _extract_urls(f.get("evidence", ""))
        category = f.get("category", "")

        if not urls:
            groups.append([f])
            group_urls.append(set())
            group_categories.append(category)
            continue

        attached = False
        for i, (g_urls, g_cat) in enumerate(zip(group_urls, group_categories)):
            if g_urls and g_cat == category and not g_urls.isdisjoint(urls):
                groups[i].append(f)
                group_urls[i] |= urls
                attached = True
                break
        if not attached:
            groups.append([f])
            group_urls.append(urls)
            group_categories.append(category)

    return [_merge_group(g) for g in groups]
