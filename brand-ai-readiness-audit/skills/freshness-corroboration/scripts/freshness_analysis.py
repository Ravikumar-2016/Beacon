"""
Freshness Analysis — Date extraction and staleness assessment.

Identifies time-sensitive content and assesses whether it may be stale:
- Explicit dates (published, modified, copyright).
- Structured data dates.
- References to past events/offers as if current.
- Content type determines time-sensitivity.

Design principle: a missing date, or content simply being old, is NEVER by
itself a staleness signal. Staleness requires (a) content that is genuinely
time-sensitive by type, AND (b) specific textual/temporal evidence that it
is no longer valid.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

# Content-type sensitivity table (mirrors references/freshness-checklist.md).
# "high": actively volatile, likely wrong if stale.
# "moderate": can go stale but changes more slowly.
# "none": not meaningfully time-sensitive (historical/evergreen).
_TIME_SENSITIVITY: dict[str, str] = {
    "price": "high", "pricing": "high", "offer": "high", "promotion": "high",
    "sale": "high", "discount": "high", "deal": "high",
    "availability": "high", "stock": "high", "in stock": "high",
    "event": "high", "webinar": "high", "conference": "high",
    "job": "high", "hiring": "high", "career": "high", "vacancy": "high",
    "version": "high", "release": "high", "update": "high",
    "leadership": "moderate", "ceo": "moderate", "team": "moderate",
    "hours": "moderate", "opening hours": "moderate",
    "policy": "moderate", "policies": "moderate",
    "service": "moderate", "services": "moderate",
    "history": "none", "founded": "none", "mission": "none",
    "about us": "none", "story": "none",
}

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)

_DATE_PATTERNS = [
    re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b"),  # ISO
    re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}}),?\s+(20\d{{2}}|19\d{{2}})\b", re.IGNORECASE),
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS})\.?,?\s+(20\d{{2}}|19\d{{2}})\b", re.IGNORECASE),
]

_COPYRIGHT_RE = re.compile(r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.IGNORECASE)

_LAST_UPDATED_RE = re.compile(
    r"(?:last\s+updated|updated\s+on|last\s+modified|last\s+revised)[:\s]*"
    r"([A-Za-z0-9,./\-\s]{4,30}?)(?:\.|<|$|\n)",
    re.IGNORECASE,
)

# "Join us in 2024!", "happening in 2023", "upcoming 2022 conference" — a
# past year referenced with present/future-tense language.
_FUTURE_TENSE_YEAR_RE = re.compile(
    r"\b(join us|happening|upcoming|don't miss|coming (?:up )?in|see you)\b[^.\n]{0,40}?\b(20\d{2}|19\d{2})\b",
    re.IGNORECASE,
)

_EXPIRY_RE = re.compile(
    r"\b(?:offer\s+(?:valid\s+)?(?:until|through|ends?)|sale\s+ends?|expires?(?:\s+on)?|"
    r"valid\s+(?:until|through))\s*:?\s*"
    rf"((?:{_MONTHS})\.?\s+\d{{1,2}},?\s+(?:20\d{{2}}|19\d{{2}})|\d{{1,2}}/\d{{1,2}}/(?:20\d{{2}}|19\d{{2}})|(?:20\d{{2}}|19\d{{2}})-\d{{2}}-\d{{2}})",
    re.IGNORECASE,
)

_MONTH_INDEX = {
    m: i + 1 for i, m in enumerate([
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    ])
}
_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date_str(raw: str) -> str | None:
    """Best-effort parse of a free-text date into an ISO 'YYYY-MM-DD' string."""
    raw = raw.strip().rstrip(".")
    m = re.match(r"^(20\d{2}|19\d{2})-(\d{2})-(\d{2})$", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.match(rf"^(\d{{1,2}})/(\d{{1,2}})/(20\d{{2}}|19\d{{2}})$", raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return None
    m = re.match(rf"^({_MONTHS})\.?\s+(\d{{1,2}}),?\s+(20\d{{2}}|19\d{{2}})$", raw, re.IGNORECASE)
    if m:
        month_name = m.group(1).lower()
        month_num = _MONTH_INDEX.get(month_name) or _MONTH_ABBR.get(month_name)
        if month_num:
            try:
                return date(int(m.group(3)), month_num, int(m.group(2))).isoformat()
            except ValueError:
                return None
    m = re.match(rf"^(\d{{1,2}})\s+({_MONTHS})\.?,?\s+(20\d{{2}}|19\d{{2}})$", raw, re.IGNORECASE)
    if m:
        month_name = m.group(2).lower()
        month_num = _MONTH_INDEX.get(month_name) or _MONTH_ABBR.get(month_name)
        if month_num:
            try:
                return date(int(m.group(3)), month_num, int(m.group(1))).isoformat()
            except ValueError:
                return None
    return None


def classify_time_sensitivity(context_text: str) -> str:
    """Classify how time-sensitive a piece of context text appears to be.

    Returns "high", "moderate", or "none" based on keyword presence, per the
    content-type table in references/freshness-checklist.md. Defaults to
    "none" (never assume time-sensitivity without a matching keyword).
    """
    if not context_text:
        return "none"
    text = context_text.lower()
    if any(kw in text for kw in _TIME_SENSITIVITY if _TIME_SENSITIVITY[kw] == "high"):
        return "high"
    if any(kw in text for kw in _TIME_SENSITIVITY if _TIME_SENSITIVITY[kw] == "moderate"):
        return "moderate"
    return "none"


def _extract_jsonld_dates(html: str) -> list[dict[str, Any]]:
    """Extract datePublished/dateModified from JSON-LD, if present."""
    found = []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return found
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in ("datePublished", "dateModified"):
                val = item.get(field)
                if isinstance(val, str) and val.strip():
                    found.append({"type": field, "value": val.strip(), "parsed": _normalize_iso(val.strip())})
    return found


def _normalize_iso(value: str) -> str | None:
    """Normalize an ISO-ish datetime string down to a date (YYYY-MM-DD)."""
    m = re.match(r"^(20\d{2}|19\d{2})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    return None


def analyze_freshness(html: str, url: str = "") -> dict[str, Any]:
    """Analyze a page for freshness signals.

    Args:
        html: Raw HTML content.
        url: Source URL.

    Returns:
        Freshness assessment with dates found and staleness signals.
        Note: presence of these signals is NOT itself a finding — the
        caller (audit_runner) must gate on time-sensitivity + evidence.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        visible_text = soup.get_text(separator=" ", strip=True)
    except Exception:
        visible_text = ""

    dates_found: list[dict[str, Any]] = _extract_jsonld_dates(html)

    copyright_match = _COPYRIGHT_RE.search(visible_text)
    if copyright_match:
        dates_found.append({
            "type": "copyright_year",
            "value": copyright_match.group(1),
            "parsed": None,
        })

    last_updated_match = _LAST_UPDATED_RE.search(visible_text)
    if last_updated_match:
        raw = last_updated_match.group(1).strip()
        dates_found.append({
            "type": "last_updated_text",
            "value": raw,
            "parsed": _parse_date_str(raw),
        })

    staleness_signals: list[dict[str, Any]] = []
    current_year = datetime.now().year

    for m in _FUTURE_TENSE_YEAR_RE.finditer(visible_text):
        year = int(m.group(2))
        if year < current_year:
            staleness_signals.append({
                "type": "past_tense_as_present",
                "detail": f"Content refers to {year} using present/upcoming language, but {year} has passed.",
                "evidence_text": m.group(0)[:160],
            })

    for m in _EXPIRY_RE.finditer(visible_text):
        raw_date = m.group(1)
        parsed = _parse_date_str(raw_date)
        if parsed:
            try:
                if datetime.fromisoformat(parsed).date() < datetime.now().date():
                    staleness_signals.append({
                        "type": "expired_offer_still_displayed",
                        "detail": f"Offer/validity language references {raw_date}, which has already passed.",
                        "evidence_text": m.group(0)[:160],
                    })
            except ValueError:
                pass

    # Date-order inversion: dateModified earlier than datePublished.
    published = next((d["parsed"] for d in dates_found if d["type"] == "datePublished" and d["parsed"]), None)
    modified = next((d["parsed"] for d in dates_found if d["type"] == "dateModified" and d["parsed"]), None)
    if published and modified and modified < published:
        staleness_signals.append({
            "type": "date_order_inversion",
            "detail": f"dateModified ({modified}) is earlier than datePublished ({published}).",
            "evidence_text": f"datePublished={published}, dateModified={modified}",
        })

    time_sensitive_content: list[dict[str, str]] = []
    for keyword, level in _TIME_SENSITIVITY.items():
        if level == "none":
            continue
        if keyword in visible_text.lower():
            time_sensitive_content.append({"category": keyword, "sensitivity": level})

    return {
        "url": url,
        "dates_found": dates_found,
        "staleness_signals": staleness_signals,
        "time_sensitive_content": time_sensitive_content,
    }


def assess_staleness(
    content_type: str,
    date_found: str | None,
    current_date: str | None = None,
) -> dict[str, Any]:
    """Assess whether content may be stale based on type and age.

    Args:
        content_type: The type of content (price, event, offer, etc.) — a
            free-text label matched against the sensitivity table.
        date_found: The date associated with the content (ISO format), or
            None if no date evidence exists.
        current_date: Current date for comparison (ISO format); defaults to
            today.

    Returns:
        Staleness assessment. Never flags staleness merely because a date
        is missing or content is old — requires both time-sensitivity and
        a specific age/expiry signal.
    """
    sensitivity = classify_time_sensitivity(content_type)
    is_time_sensitive = sensitivity in ("high", "moderate")

    if not is_time_sensitive:
        return {
            "content_type": content_type,
            "is_time_sensitive": False,
            "potentially_stale": False,
            "reason": "Content type is not meaningfully time-sensitive.",
        }

    if not date_found:
        return {
            "content_type": content_type,
            "is_time_sensitive": True,
            "potentially_stale": False,
            "reason": "No date evidence available; cannot assess staleness confidently.",
        }

    try:
        found_dt = datetime.fromisoformat(date_found).date()
    except ValueError:
        return {
            "content_type": content_type,
            "is_time_sensitive": True,
            "potentially_stale": False,
            "reason": "Date evidence could not be parsed; cannot assess staleness confidently.",
        }

    ref_dt = datetime.fromisoformat(current_date).date() if current_date else datetime.now().date()
    age_days = (ref_dt - found_dt).days

    # Thresholds only apply to "high" sensitivity content, and only when the
    # date has clearly passed (age_days > 0); "moderate" content is far more
    # tolerant of age (e.g. leadership/hours change slowly and legitimately).
    if sensitivity == "high" and age_days > 90:
        return {
            "content_type": content_type,
            "is_time_sensitive": True,
            "potentially_stale": True,
            "reason": f"Time-sensitive content ({content_type}) is dated {date_found}, {age_days} days ago.",
        }

    return {
        "content_type": content_type,
        "is_time_sensitive": True,
        "potentially_stale": False,
        "reason": "Content is time-sensitive but within a normal freshness window.",
    }
