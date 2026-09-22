"""
CTA Analysis — Call-to-action detection, quality assessment, and specificity.

Detects CTAs on pages and assesses their quality:
- Presence of meaningful CTAs.
- Specificity (generic vs descriptive).
- Visibility and accessibility.
"""

from typing import Any

from bs4 import BeautifulSoup


# Common CTA patterns
GENERIC_CTA_TEXTS = {
    "click here", "submit", "go", "learn more", "read more",
    "more", "continue", "next", "see more", "view",
}

STRONG_CTA_PATTERNS = [
    "get started", "start free", "sign up", "try free", "book demo",
    "request demo", "view pricing", "compare plans", "contact sales",
    "download", "buy now", "add to cart", "schedule", "subscribe",
    "view products", "see plans", "start trial",
]


def analyze_ctas(html: str, url: str = "") -> dict[str, Any]:
    """Analyze CTAs on a page.

    Args:
        html: Raw HTML content.
        url: Source URL.

    Returns:
        CTA assessment with inventory and quality signals.
    """
    soup = BeautifulSoup(html, "html.parser")
    ctas = _extract_ctas(soup)

    generic_count = sum(1 for c in ctas if c.get("quality") == "generic")
    specific_count = sum(1 for c in ctas if c.get("quality") == "specific")

    return {
        "url": url,
        "total_ctas": len(ctas),
        "ctas": ctas,
        "generic_count": generic_count,
        "specific_count": specific_count,
        "has_primary_cta": specific_count > 0,
    }


def _extract_ctas(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract potential CTAs from the page."""
    ctas = []

    # Buttons
    for btn in soup.find_all(["button", "a"]):
        text = btn.get_text(strip=True)
        if not text or len(text) > 100:
            continue

        # Check if it looks like a CTA
        is_button = btn.name == "button"
        has_btn_class = any(
            "btn" in c.lower() or "button" in c.lower() or "cta" in c.lower()
            for c in btn.get("class", [])
        )
        has_role = btn.get("role") == "button"

        if is_button or has_btn_class or has_role:
            quality = _assess_cta_quality(text)
            ctas.append({
                "text": text,
                "tag": btn.name,
                "href": btn.get("href", ""),
                "quality": quality,
            })

    return ctas


def _assess_cta_quality(text: str) -> str:
    """Assess CTA text quality: 'generic', 'specific', or 'moderate'."""
    lower = text.lower().strip()

    if lower in GENERIC_CTA_TEXTS:
        return "generic"

    for pattern in STRONG_CTA_PATTERNS:
        if pattern in lower:
            return "specific"

    # If it contains action verbs + specifics, it's moderate-to-good
    if len(lower.split()) >= 2:
        return "moderate"

    return "generic"
