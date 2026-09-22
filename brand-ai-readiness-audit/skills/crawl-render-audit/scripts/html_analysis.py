"""
HTML Analysis — Raw HTML content analysis.

Extracts visible text, headings, semantic structure, and identifies
content locked in non-text formats (images, canvas, inaccessible UI).
"""

import re
from typing import Any

from bs4 import BeautifulSoup, Comment, Tag


def analyze_html(html: str, url: str = "") -> dict[str, Any]:
    """Analyze raw HTML content for discoverability signals.

    Args:
        html: Raw HTML string.
        url: Source URL for context.

    Returns:
        Dictionary with text content, headings, semantic elements, and signals.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract text ONCE on a copy to avoid decompose mutation issues
    text = extract_visible_text(html)
    headings = extract_headings(soup)

    return {
        "url": url,
        "text": text,
        "text_length": len(text),
        "headings": headings,
        "semantic_sections": detect_semantic_sections(soup),
        "images_with_alt": count_images_with_alt(soup),
        "non_text_content_signals": detect_non_text_content(soup),
        "iframes": detect_iframes(soup),
        "forms": detect_forms(soup),
    }


def extract_visible_text(html_or_soup: str | BeautifulSoup) -> str:
    """Extract visible text content, stripping scripts/styles.

    Accepts either raw HTML string or BeautifulSoup object.
    Always works on a COPY to avoid mutating the original soup.
    """
    if isinstance(html_or_soup, str):
        soup = BeautifulSoup(html_or_soup, "html.parser")
    else:
        # Work on a copy to avoid mutation
        soup = BeautifulSoup(str(html_or_soup), "html.parser")

    for tag in soup(["script", "style", "noscript", "meta", "link", "template"]):
        tag.decompose()
    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    return soup.get_text(separator=" ", strip=True)


def extract_headings(soup: BeautifulSoup) -> dict[str, list[str]]:
    """Extract all headings organized by level."""
    headings: dict[str, list[str]] = {}
    for level in range(1, 7):
        tag_name = f"h{level}"
        found = [h.get_text(strip=True) for h in soup.find_all(tag_name)]
        if found:
            headings[tag_name] = found
    return headings


def detect_semantic_sections(soup: BeautifulSoup) -> dict[str, int]:
    """Count semantic HTML5 elements."""
    elements = ["main", "article", "section", "nav", "aside", "header", "footer"]
    return {el: len(soup.find_all(el)) for el in elements if soup.find_all(el)}


def count_images_with_alt(soup: BeautifulSoup) -> dict[str, int]:
    """Count images and check alt text presence."""
    images = soup.find_all("img")
    with_alt = sum(1 for img in images if img.get("alt", "").strip())
    return {
        "total": len(images),
        "with_alt": with_alt,
        "without_alt": len(images) - with_alt,
    }


def detect_non_text_content(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Detect potential important content locked in non-text formats.

    Returns signals — these are NOT automatic findings.
    Context is needed to decide if they represent real problems.
    """
    signals: list[dict[str, Any]] = []

    # Canvas elements (charts/data rendered as canvas)
    canvases = soup.find_all("canvas")
    if canvases:
        signals.append({
            "type": "canvas",
            "count": len(canvases),
            "note": "Canvas elements detected — content inside is not machine-readable.",
        })

    # Heavy SVG usage that might contain important text
    svgs = soup.find_all("svg")
    svg_with_text = 0
    for svg in svgs:
        if svg.find("text") or svg.find("tspan"):
            svg_with_text += 1
    if svg_with_text > 0:
        signals.append({
            "type": "svg_text",
            "count": svg_with_text,
            "note": f"{svg_with_text} SVG element(s) contain text nodes — this text may not be extractable by simple crawlers.",
        })

    # Images that might contain important textual information
    # (images in contexts suggesting they carry key data, not just decoration)
    important_img_contexts = _detect_images_as_text(soup)
    if important_img_contexts:
        signals.append({
            "type": "image_as_text",
            "count": len(important_img_contexts),
            "details": important_img_contexts[:5],  # Cap at 5 examples
            "note": "Images detected in contexts suggesting they may carry important textual information.",
        })

    # Object/embed elements
    objects = soup.find_all(["object", "embed"])
    if objects:
        signals.append({
            "type": "embedded_objects",
            "count": len(objects),
            "note": "Embedded objects detected — content may not be machine-readable.",
        })

    return signals


def _detect_images_as_text(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Detect images that likely carry important textual information.

    Heuristic: images inside table cells, pricing sections, spec areas,
    or with alt text suggesting data content (prices, specs, schedules).
    """
    suspects: list[dict[str, str]] = []

    # Patterns suggesting data-carrying images
    data_patterns = re.compile(
        r"(price|pricing|cost|specification|spec|schedule|menu|hour|rate|tariff|plan|table|chart|graph|data)",
        re.IGNORECASE,
    )

    for img in soup.find_all("img"):
        alt = img.get("alt", "") or ""
        src = img.get("src", "") or ""
        # Check parent context
        parent = img.parent
        parent_text = ""
        parent_classes = ""
        if parent:
            parent_classes = " ".join(parent.get("class", []))
            parent_text = parent.get_text(strip=True)[:100]

        # Heuristic: image alt or parent context suggests data content
        context = f"{alt} {parent_classes} {parent_text}"
        if data_patterns.search(context):
            suspects.append({
                "src": src[:200],
                "alt": alt[:100],
                "context": context[:200],
            })

    return suspects


def detect_iframes(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Detect iframes which contain content invisible to simple crawlers."""
    iframes = []
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "") or ""
        title = iframe.get("title", "") or ""
        if src:
            iframes.append({"src": src[:200], "title": title[:100]})
    return iframes


def detect_forms(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Detect forms on the page (for context, not for submission)."""
    forms = []
    for form in soup.find_all("form"):
        action = form.get("action", "") or ""
        method = form.get("method", "get")
        inputs = [inp.get("name", "") for inp in form.find_all("input") if inp.get("name")]
        forms.append({
            "action": action[:200],
            "method": method,
            "input_count": len(inputs),
        })
    return forms


def detect_loading_placeholders(html: str) -> list[str]:
    """Detect patterns suggesting content is loaded dynamically.

    Returns list of detected placeholder patterns.
    """
    patterns = [
        r"loading\.{0,3}",
        r"please\s+wait",
        r"spinner",
        r"skeleton",
        r"lazy-?load",
        r"data-src=",
        r"ng-app",
        r"__NEXT_DATA__",
        r"__NUXT__",
        r"react-root",
        r'id="app"\s*>[\s]*<',
        r'id="root"\s*>[\s]*<',
    ]
    found = []
    html_lower = html.lower()
    for pattern in patterns:
        if re.search(pattern, html_lower):
            found.append(pattern)
    return found
