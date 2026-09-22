"""
Metadata Analysis — Title, description, canonical, and robots meta extraction.

Extracts and validates page-level metadata for discoverability:
- <title> tag
- <meta name="description">
- <link rel="canonical">
- <meta name="robots">
- X-Robots-Tag header
"""

from typing import Any

from bs4 import BeautifulSoup, Tag


def extract_metadata(html: str, url: str = "", headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Extract all relevant metadata from a page.

    Args:
        html: Raw HTML content.
        url: The page URL.
        headers: HTTP response headers (keys should be lowercase).

    Returns:
        Dictionary with title, description, canonical, robots directives,
        and Open Graph properties.
    """
    soup = BeautifulSoup(html, "html.parser")
    headers = headers or {}

    return {
        "url": url,
        "title": _extract_title(soup),
        "description": _extract_meta_description(soup),
        "canonical": _extract_canonical(soup),
        "robots_meta": _extract_robots_meta(soup),
        # X-Robots-Tag may be multi-valued; normalize to lowercase for checks
        "x_robots_tag": headers.get("x-robots-tag", "").strip().lower(),
        "og_title": _extract_og(soup, "og:title"),
        "og_description": _extract_og(soup, "og:description"),
        "og_site_name": _extract_og(soup, "og:site_name"),
    }


def assess_title_quality(title: str | None) -> dict[str, Any]:
    """Assess whether a page title is meaningful.

    Returns:
        Assessment with quality level and reason.
    """
    if not title:
        return {"quality": "missing", "reason": "No <title> tag found."}

    title = title.strip()
    if not title:
        return {"quality": "empty", "reason": "Empty <title> tag."}

    generic_titles = {
        "home", "homepage", "welcome", "untitled", "document",
        "page", "new page", "test", "index",
    }
    if title.lower() in generic_titles:
        return {"quality": "generic", "reason": f"Generic title: '{title}'"}

    if len(title) < 10:
        return {"quality": "weak", "reason": f"Very short title: '{title}'"}

    if len(title) > 160:
        return {"quality": "overly_long", "reason": f"Title exceeds 160 chars ({len(title)} chars): '{title[:80]}...'"}

    return {"quality": "good", "reason": None}


def is_indexing_blocked(robots_meta: str | None, x_robots_tag: str) -> bool:
    """Return True if either robots directive prevents indexing.

    Checks for noindex or none directives in both the meta tag and
    the X-Robots-Tag HTTP header.
    """
    blocking_directives = ("noindex", "none")
    for directive in blocking_directives:
        if robots_meta and directive in robots_meta.lower():
            return True
        if x_robots_tag and directive in x_robots_tag.lower():
            return True
    return False


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract <title> tag content."""
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else None


def _extract_meta_description(soup: BeautifulSoup) -> str | None:
    """Extract <meta name='description'> content."""
    meta = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "description"})
    if meta and isinstance(meta, Tag):
        content = meta.get("content", "")
        return content.strip() if isinstance(content, str) else None
    return None


def _extract_canonical(soup: BeautifulSoup) -> str | None:
    """Extract <link rel='canonical'> href.

    BeautifulSoup stores 'rel' as a list for link elements, so we check
    both the list form and the string form to handle all parsers correctly.
    """
    # find() with attrs dict matches rel as a list item
    for link in soup.find_all("link"):
        if not isinstance(link, Tag):
            continue
        rel = link.get("rel", [])
        # rel may be a list (html.parser) or a string (some edge cases)
        rel_values = rel if isinstance(rel, list) else [rel]
        if "canonical" in rel_values:
            href = link.get("href", "")
            return href.strip() if isinstance(href, str) else None
    return None


def _extract_robots_meta(soup: BeautifulSoup) -> str | None:
    """Extract <meta name='robots'> content."""
    meta = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "robots"})
    if meta and isinstance(meta, Tag):
        content = meta.get("content", "")
        return content.strip() if isinstance(content, str) else None
    return None


def _extract_og(soup: BeautifulSoup, property_name: str) -> str | None:
    """Extract an OpenGraph meta property."""
    meta = soup.find("meta", attrs={"property": property_name})
    if meta and isinstance(meta, Tag):
        content = meta.get("content", "")
        return content.strip() if isinstance(content, str) else None
    return None
