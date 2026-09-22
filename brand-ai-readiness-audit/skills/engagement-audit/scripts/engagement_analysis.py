"""
Engagement Analysis — Aggregation of engagement signals into structured evidence.

Combines results from orientation, navigation, CTA, link health, and viewport
checks into a unified engagement assessment per page.
"""

from typing import Any


def aggregate_engagement(
    orientation: dict[str, Any],
    navigation: dict[str, Any],
    ctas: dict[str, Any],
    link_health: list[dict[str, Any]],
    viewport: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate engagement signals for a page.

    Args:
        orientation: Output from page_orientation.assess_orientation().
        navigation: Output from navigation_analysis.analyze_navigation().
        ctas: Output from cta_analysis.analyze_ctas().
        link_health: Output from link_health.check_links().
        viewport: Output from viewport_check.check_viewport().

    Returns:
        Aggregated engagement evidence.
    """
    broken_links = [l for l in link_health if l.get("is_broken")]

    return {
        "url": orientation.get("url", ""),
        "orientation": {
            "clear": orientation.get("has_h1") and orientation.get("org_identity_visible"),
            "signals": orientation,
        },
        "navigation": {
            "present": navigation.get("has_main_navigation", False),
            "link_count": navigation.get("nav_link_count", 0),
            "ambiguous_labels": navigation.get("label_assessment", []),
        },
        "ctas": {
            "present": ctas.get("total_ctas", 0) > 0,
            "has_specific": ctas.get("has_primary_cta", False),
            "generic_only": ctas.get("generic_count", 0) > 0 and ctas.get("specific_count", 0) == 0,
        },
        "link_health": {
            "total_checked": len(link_health),
            "broken_count": len(broken_links),
            "broken_links": broken_links,
        },
        "viewport": viewport,
    }


def detect_intrusive_interruptions(html: str, url: str = "") -> list[dict[str, Any]]:
    """Detect intrusive interruptions that block content access.

    Looks for:
    - Full-screen modals/popups.
    - Mandatory signup walls.
    - Blocking overlays.

    Each DOM element is counted at most once, even if its class attribute
    matches multiple interruption keywords (e.g. class="modal popup overlay")
    — otherwise a single element would be reported as several separate
    interruptions, inflating both the signal count and the evidence with
    duplicate copies of the same text (confirmed on a real unseen site).

    Returns:
        List of detected interruption signals, one per unique element.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    modal_indicators = ["modal", "popup", "overlay", "interstitial", "dialog"]
    matched_keywords_by_id: dict[int, list[str]] = {}
    elements_by_id: dict[int, Any] = {}
    for indicator in modal_indicators:
        for el in soup.find_all(attrs={"class": lambda c: c and indicator in str(c).lower()}):
            eid = id(el)
            matched_keywords_by_id.setdefault(eid, []).append(indicator)
            elements_by_id[eid] = el

    signals = []
    for eid, keywords in matched_keywords_by_id.items():
        el = elements_by_id[eid]
        # Check if it might be blocking (has display styles or is large)
        style = el.get("style", "")
        if "display: none" in style.lower() or "display:none" in style.lower():
            continue
        text = el.get_text(separator=" ", strip=True)[:200]
        if not text:
            continue
        unique_keywords = sorted(set(keywords))
        signals.append({
            "type": unique_keywords[0],
            "matched_keywords": unique_keywords,
            "text_preview": text,
            "note": f"Potential {'/'.join(unique_keywords)} element detected — verify if it blocks content.",
        })

    return signals


def assess_trust_signals(html: str, url: str = "") -> dict[str, Any]:
    """Assess presence of trust/confidence signals.

    Returns:
        Dictionary of trust signal presence.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True).lower()

    return {
        "url": url,
        "has_contact_info": any(
            term in text for term in ["contact", "email", "phone", "tel:", "mailto:"]
        ),
        "has_about_info": any(
            term in text for term in ["about us", "about the", "our story", "our mission"]
        ),
        "has_privacy_policy": any(
            term in text for term in ["privacy policy", "privacy notice", "data protection"]
        ),
        "has_terms": any(
            term in text for term in ["terms of service", "terms and conditions", "terms of use"]
        ),
    }
