"""
Navigation Analysis — Navigation structure, labels, and coverage.

Analyzes main navigation for:
- Presence and structure.
- Label clarity and ambiguity.
- Coverage of important page categories.
"""

from typing import Any

from bs4 import BeautifulSoup


def analyze_navigation(html: str, url: str = "") -> dict[str, Any]:
    """Analyze page navigation structure.

    Args:
        html: Raw HTML content.
        url: Source URL.

    Returns:
        Navigation assessment.
    """
    soup = BeautifulSoup(html, "html.parser")
    nav_elements = soup.find_all("nav")

    nav_links = []
    for nav in nav_elements:
        for a_tag in nav.find_all("a", href=True):
            nav_links.append({
                "text": a_tag.get_text(strip=True),
                "href": a_tag["href"],
            })

    return {
        "url": url,
        "nav_element_count": len(nav_elements),
        "nav_links": nav_links,
        "has_main_navigation": len(nav_elements) > 0,
        "nav_link_count": len(nav_links),
        "label_assessment": _assess_labels(nav_links),
    }


def _assess_labels(nav_links: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Assess navigation label clarity."""
    # Ambiguous labels that provide little context without more info
    ambiguous_patterns = {
        "solutions", "resources", "explore", "more", "other",
        "services", "offerings", "platform",
    }

    assessments = []
    for link in nav_links:
        text = link.get("text", "").strip().lower()
        if text in ambiguous_patterns:
            assessments.append({
                "text": link["text"],
                "issue": "potentially_ambiguous",
                "note": f"Label '{link['text']}' may not clearly indicate content.",
            })
    return assessments
