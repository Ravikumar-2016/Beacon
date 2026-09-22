"""
Fact Consistency — Cross-page fact extraction and contradiction detection.

Extracts important facts (prices, contact info, hours, founding year) from
multiple pages and compares them to identify contradictions.

Design principle: only compare the SAME field for the SAME entity/context.
Different products having different prices, regional variants, or clearly
different contexts are never contradictions — only a genuine same-field
mismatch (e.g. two different phone numbers both presented as "the" contact
number) counts.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")
_PRICE_RE = re.compile(
    r"(?:[$€£¥₹]|USD|EUR|GBP|INR)\s*\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?"
)
# Deliberately excludes the bare word "since": "since <year>" is extremely
# common in non-founding contexts ("effective since 2024", "available since
# 2024") and, unlike "founded"/"established"/"formed"/"created"/"launched",
# carries no organizational-founding meaning on its own -- confirmed as a
# real false positive on an unseen site (a "since 2024" mention on a policy
# page was compared against an unrelated "since 2007" mention elsewhere as
# if both stated the company's founding year).
_FOUNDED_RE = re.compile(
    r"\b(?:founded|established|formed|created|launched|est\.?)\b[^.\n\d]{0,15}(\d{4})",
    re.IGNORECASE,
)
_DAY_RE = re.compile(
    r"\b(mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\b")

_DAY_CANON = {
    "mon": "mon", "monday": "mon", "tue": "tue", "tues": "tue", "tuesday": "tue",
    "wed": "wed", "wednesday": "wed", "thu": "thu", "thurs": "thu", "thursday": "thu",
    "fri": "fri", "friday": "fri", "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
}


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if 7 <= len(digits) <= 15:
        return digits
    return None


def _normalize_price(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def extract_facts(html: str, url: str = "", depth: int = 1) -> dict[str, Any]:
    """Extract important verifiable facts from a page.

    Extracts:
    - Prices and currencies (associated with the page's own product/H1 name).
    - Contact information (phone, email), tagged by whether it appeared in
      a <footer> (treated as an "official" site-wide declaration).
    - Opening hours (lines containing both a day name and a time).
    - Founding/established year mentions.

    Args:
        html: Raw HTML content.
        url: Source URL.
        depth: Crawl depth of this page (0 = homepage), set by the caller.
            Used to exclude the homepage from product/price extraction (see
            below).

    Returns:
        Dictionary of extracted facts with their locations.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return {"url": url, "prices": [], "contacts": [], "hours": [], "products": [], "dates": []}

    footer = soup.find("footer")
    footer_text = footer.get_text(separator=" ", strip=True) if footer else ""
    body_text = soup.get_text(separator=" ", strip=True)
    lines_text = soup.get_text(separator="\n", strip=True)

    contacts: list[dict[str, Any]] = []
    seen_emails: set[str] = set()
    for m in _EMAIL_RE.finditer(body_text):
        val = m.group(0).lower()
        if val in seen_emails:
            continue
        seen_emails.add(val)
        contacts.append({"type": "email", "value": val, "in_footer": val in footer_text.lower()})

    seen_phones: set[str] = set()
    for m in _PHONE_RE.finditer(body_text):
        cleaned = _clean_phone(m.group(0))
        if not cleaned or cleaned in seen_phones:
            continue
        seen_phones.add(cleaned)
        contacts.append({
            "type": "phone", "value": cleaned, "raw": m.group(0).strip(),
            "in_footer": cleaned in re.sub(r"\D", "", footer_text),
        })

    hours: list[dict[str, Any]] = []
    for line in lines_text.split("\n"):
        days = [_DAY_CANON[d.lower()] for d in _DAY_RE.findall(line)]
        times = _TIME_RE.findall(line) or _TIME_RE.findall(line)
        time_matches = _TIME_RE.findall(line)
        if days and time_matches:
            hours.append({"raw": line.strip()[:200], "days": sorted(set(days)), "times": _TIME_RE.findall(line)})

    dates: list[dict[str, Any]] = []
    founded_match = _FOUNDED_RE.search(body_text)
    if founded_match:
        dates.append({"type": "founded_year", "value": int(founded_match.group(1)), "raw": founded_match.group(0)[:80]})

    # Product/price context: the page's own primary heading (if any) paired
    # with the first price mentioned on the page. This deliberately only
    # supports comparing the SAME product name across pages — different
    # product names are never compared against each other.
    # The homepage is excluded: its H1 is essentially never a specific
    # product name (e.g. a personalized-feed label like "For You"), and a
    # homepage typically mentions many unrelated prices, so "the first price
    # on the page" is not meaningfully tied to that H1 (confirmed on a real
    # unseen site in Stage 7).
    prices: list[dict[str, Any]] = []
    h1 = soup.find("h1")
    product_name = h1.get_text(strip=True) if h1 else None
    if depth != 0:
        price_match = _PRICE_RE.search(body_text)
        if product_name and price_match:
            value = _normalize_price(price_match.group(0))
            if value is not None:
                prices.append({"product_name": product_name, "raw": price_match.group(0), "value": value})

    return {
        "url": url,
        "prices": prices,
        "contacts": contacts,
        "hours": hours,
        "products": [product_name] if product_name else [],
        "dates": dates,
    }


def _normalize_product_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def find_contradictions(
    facts_by_page: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare facts across pages to find contradictions.

    Only same-field, same-entity/context comparisons are made:
    - Contact info: compared only among "official" declarations (found in a
      <footer>, present on essentially every page of a site) — a phone
      number appearing once in unrelated body text is not compared. Two
      values are only a contradiction if they are declared on disjoint sets
      of pages — a single page listing two numbers together (e.g. a sales
      line and a support line: "Call: 044-1234 / 044-5678") is two valid
      alternatives presented together, not a contradiction.
    - Hours: compared only when the same day is mentioned with a different
      time range on different pages.
    - Founding year: compared across all pages that mention one at all.
    - Prices: compared only when the SAME product/page-heading name recurs
      with a different price on a different page.

    Args:
        facts_by_page: List of fact dicts from different pages.

    Returns:
        List of contradiction signals with evidence.
    """
    contradictions: list[dict[str, Any]] = []

    # --- Contact info (official/footer declarations only) ---
    for field in ("email", "phone"):
        value_pages: dict[str, set[str]] = {}
        for page in facts_by_page:
            url = page.get("url", "")
            for c in page.get("contacts", []):
                if c.get("type") != field or not c.get("in_footer"):
                    continue
                value_pages.setdefault(c["value"], set()).add(url)

        # Only a genuine contradiction when two different values are each
        # declared on their OWN, non-overlapping page(s) — if any page
        # presents both values together, they're alternatives, not a
        # conflict (see docstring).
        distinct_values = list(value_pages.keys())
        conflicting_pair = None
        for i in range(len(distinct_values)):
            for j in range(i + 1, len(distinct_values)):
                v_a, v_b = distinct_values[i], distinct_values[j]
                if value_pages[v_a].isdisjoint(value_pages[v_b]):
                    conflicting_pair = (v_a, v_b)
                    break
            if conflicting_pair:
                break

        if conflicting_pair:
            val_a, val_b = conflicting_pair
            url_a, url_b = sorted(value_pages[val_a])[0], sorted(value_pages[val_b])[0]
            contradictions.append({
                "field": field,
                "value_a": val_a, "page_a": url_a,
                "value_b": val_b, "page_b": url_b,
                "detail": f"Footer {field} differs across pages: '{val_a}' ({url_a}) vs '{val_b}' ({url_b}).",
                "severity_hint": "medium",
            })

    # --- Founding year ---
    years: dict[int, str] = {}
    for page in facts_by_page:
        for d in page.get("dates", []):
            if d.get("type") == "founded_year" and d["value"] not in years:
                years[d["value"]] = page.get("url", "")
    if len(years) > 1:
        items = list(years.items())
        (year_a, url_a), (year_b, url_b) = items[0], items[1]
        contradictions.append({
            "field": "founding_year",
            "value_a": str(year_a), "page_a": url_a,
            "value_b": str(year_b), "page_b": url_b,
            "detail": f"Founding year differs across pages: {year_a} ({url_a}) vs {year_b} ({url_b}).",
            "severity_hint": "medium",
        })

    # --- Hours (same day, different time range) ---
    day_times: dict[str, tuple[str, str]] = {}  # day -> (times_str, url)
    for page in facts_by_page:
        url = page.get("url", "")
        for h in page.get("hours", []):
            times_str = ",".join(h.get("times", []))
            for day in h.get("days", []):
                if day not in day_times:
                    day_times[day] = (times_str, url)
                else:
                    prev_times, prev_url = day_times[day]
                    if prev_times and times_str and prev_times != times_str and prev_url != url:
                        contradictions.append({
                            "field": "hours",
                            "value_a": f"{day}: {prev_times}", "page_a": prev_url,
                            "value_b": f"{day}: {times_str}", "page_b": url,
                            "detail": f"Opening hours for {day} differ: '{prev_times}' ({prev_url}) vs '{times_str}' ({url}).",
                            "severity_hint": "medium",
                        })

    # --- Prices (same product name, different price) ---
    product_prices: dict[str, tuple[float, str, str]] = {}  # normalized name -> (value, raw, url)
    for page in facts_by_page:
        url = page.get("url", "")
        for p in page.get("prices", []):
            key = _normalize_product_name(p["product_name"])
            if key not in product_prices:
                product_prices[key] = (p["value"], p["raw"], url)
            else:
                prev_value, prev_raw, prev_url = product_prices[key]
                if prev_url != url and abs(prev_value - p["value"]) > 0.01:
                    contradictions.append({
                        "field": "price",
                        "value_a": prev_raw, "page_a": prev_url,
                        "value_b": p["raw"], "page_b": url,
                        "detail": (
                            f"Price for '{p['product_name']}' differs across pages: "
                            f"{prev_raw} ({prev_url}) vs {p['raw']} ({url})."
                        ),
                        "severity_hint": "high",
                    })

    return contradictions
