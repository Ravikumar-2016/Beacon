"""
Page Orientation — Landing-page identity, purpose, and organization clarity.

Checks whether a visitor arriving from an AI referral can immediately understand:
- What this page is about.
- Who the organization is.
- What the page's purpose is.
"""

from typing import Any

from bs4 import BeautifulSoup


def assess_orientation(html: str, url: str = "") -> dict[str, Any]:
    """Assess page orientation clarity.

    Args:
        html: Raw HTML content.
        url: Source URL.

    Returns:
        Orientation assessment with specific signals.
    """
    soup = BeautifulSoup(html, "html.parser")

    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else None

    # Check for organization identity signals
    org_visible = bool(
        _find_logo(soup)
        or _find_org_in_header(soup)
    )

    # Check for page purpose clarity
    has_intro = _has_introductory_text(soup)

    return {
        "url": url,
        "has_h1": bool(h1_tags),
        "h1_content": h1_tags,
        "has_title": bool(title_text),
        "title": title_text,
        "org_identity_visible": org_visible,
        "has_introductory_text": has_intro,
        "has_breadcrumbs": _has_breadcrumbs(soup),
    }


def _find_logo(soup: BeautifulSoup) -> bool:
    """Check if a logo is present."""
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").lower()
        cls = " ".join(img.get("class", [])).lower()
        if "logo" in alt or "logo" in cls:
            return True
    return False


def _find_org_in_header(soup: BeautifulSoup) -> bool:
    """Check if organization name is visible in header."""
    header = soup.find("header")
    if header and len(header.get_text(strip=True)) > 0:
        return True
    return False


def _has_introductory_text(soup: BeautifulSoup) -> bool:
    """Check if page has meaningful introductory text after H1."""
    h1 = soup.find("h1")
    if h1:
        # Look for paragraph text near the H1
        sibling = h1.find_next_sibling()
        while sibling:
            if hasattr(sibling, "name") and sibling.name == "p":
                text = sibling.get_text(strip=True)
                if len(text) > 30:
                    return True
            sibling = sibling.find_next_sibling() if hasattr(sibling, "find_next_sibling") else None
            # Only check next few siblings
            break
    return False


def _has_breadcrumbs(soup: BeautifulSoup) -> bool:
    """Check if breadcrumb navigation is present."""
    # Check for BreadcrumbList schema
    for script in soup.find_all("script", type="application/ld+json"):
        if "BreadcrumbList" in (script.string or ""):
            return True
    # Check for common breadcrumb patterns
    for nav in soup.find_all("nav"):
        aria = (nav.get("aria-label") or "").lower()
        if "breadcrumb" in aria:
            return True
    return False
