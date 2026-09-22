"""
Link Analysis — Internal link graph and connectivity analysis.

Builds an internal link graph from crawled pages and identifies
pages that are disconnected from site navigation.
"""

from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def extract_links(html: str, base_url: str) -> dict[str, Any]:
    """Extract all links from HTML and classify them."""
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc

    internal = []
    external = []
    seen_hrefs: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(absolute)
        text = a_tag.get_text(strip=True)

        if absolute in seen_hrefs:
            continue
        seen_hrefs.add(absolute)

        link_info = {
            "href": absolute,
            "text": text,
            "is_navigation": _is_in_nav(a_tag),
        }

        if parsed.netloc == base_domain or parsed.netloc.endswith(f".{base_domain}"):
            internal.append(link_info)
        else:
            external.append(link_info)

    return {
        "internal_count": len(internal),
        "external_count": len(external),
        "internal": internal,
        "external": external,
    }


def build_link_graph(pages: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build an internal link graph from crawled pages.

    Args:
        pages: List of page dicts with 'url' and 'links' keys.
               'links' should have an 'internal' list of {href: ...} dicts.

    Returns:
        Adjacency list: {source_url: [target_url, ...]}.
    """
    graph: dict[str, list[str]] = {}
    for page in pages:
        url = page.get("url", "")
        links_data = page.get("links", {})
        if isinstance(links_data, dict):
            targets = [link.get("href", "") for link in links_data.get("internal", [])]
        else:
            targets = []
        graph[url] = targets
    return graph


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent comparison.

    Strips trailing slashes from the path and lowercases scheme and host.
    Path case is preserved (paths can be case-sensitive on some servers).
    Fragment and query string are dropped.

    Examples:
        "https://Example.com/about/" -> "https://example.com/about"
        "https://example.com"        -> "https://example.com/"
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    return f"{scheme}://{netloc}{path}"


def find_orphan_pages(
    link_graph: dict[str, list[str]],
    all_known_urls: set[str],
    homepage_url: str = "",
) -> list[str]:
    """Find pages in all_known_urls that have NO inbound links from crawled pages.

    An orphan is a page that exists (e.g., in sitemap) but is never linked
    to from any of the pages we crawled.

    The homepage is ALWAYS excluded as it is the primary entry point and
    never truly an orphan. Previously this function claimed to exclude the
    homepage but never did (bug now fixed).

    URL normalization handles trailing-slash mismatches between sitemap URLs
    and linked-to URLs to avoid false-positive orphan detections.

    Args:
        link_graph: Adjacency list built by build_link_graph().
        all_known_urls: Full set of known URLs (sitemap + crawled).
        homepage_url: The site homepage URL to exclude from orphan candidates.

    Returns:
        List of URLs that have no inbound links and are not the homepage.
    """
    # Collect all URLs that are targets of at least one internal link
    linked_to: set[str] = set()
    for targets in link_graph.values():
        linked_to.update(targets)

    # Normalize for comparison to avoid trailing-slash false positives
    normalized_linked_to = {normalize_url(u) for u in linked_to}
    normalized_homepage = normalize_url(homepage_url) if homepage_url else ""

    orphans = []
    for url in all_known_urls:
        normalized = normalize_url(url)
        # Skip the homepage — it is always the known entry point
        if normalized_homepage and normalized == normalized_homepage:
            continue
        # A page is an orphan if no crawled page links to it
        if normalized not in normalized_linked_to:
            orphans.append(url)

    return orphans


def find_disconnected_pages(
    link_graph: dict[str, list[str]],
    homepage_url: str,
) -> list[str]:
    """Find crawled pages not reachable from the homepage via link traversal.

    Uses BFS from homepage through the link graph.
    Uses collections.deque for O(1) popleft instead of list.pop(0).
    """
    if homepage_url not in link_graph:
        return list(link_graph.keys())

    reachable: set[str] = set()
    queue: deque[str] = deque([homepage_url])
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        for target in link_graph.get(current, []):
            if target not in reachable and target in link_graph:
                queue.append(target)

    return [url for url in link_graph if url not in reachable]


def analyze_nav_coverage(
    pages: list[dict[str, Any]],
    homepage_url: str,
) -> dict[str, Any]:
    """Analyze which important page categories are linked from homepage nav.

    Returns assessment of navigation coverage.
    """
    homepage_data = None
    for p in pages:
        if p.get("url") == homepage_url:
            homepage_data = p
            break

    if not homepage_data:
        return {"checked": False, "reason": "homepage_not_in_crawl"}

    links_data = homepage_data.get("links", {})
    if isinstance(links_data, dict):
        nav_links = [
            lnk for lnk in links_data.get("internal", [])
            if lnk.get("is_navigation", False)
        ]
    else:
        nav_links = []

    nav_hrefs = {lnk.get("href", "") for lnk in nav_links}
    nav_texts = {lnk.get("text", "").lower() for lnk in nav_links}

    # Check for common important page categories
    important_patterns = {
        "products": ["product", "shop", "store", "catalog"],
        "services": ["service", "solution"],
        "pricing": ["pricing", "price", "plan"],
        "about": ["about", "company", "team"],
        "contact": ["contact", "support", "help"],
    }

    coverage: dict[str, bool] = {}
    for category, patterns in important_patterns.items():
        found = False
        for pattern in patterns:
            for text in nav_texts:
                if pattern in text:
                    found = True
                    break
            if found:
                break
            for href in nav_hrefs:
                if pattern in href.lower():
                    found = True
                    break
            if found:
                break
        coverage[category] = found

    return {
        "checked": True,
        "nav_link_count": len(nav_links),
        "total_internal_links": links_data.get("internal_count", 0) if isinstance(links_data, dict) else 0,
        "coverage": coverage,
    }


def _is_in_nav(tag: Any) -> bool:
    """Check if a link is inside a <nav> element."""
    parent = tag.parent
    depth = 0
    while parent and depth < 10:
        if hasattr(parent, "name") and parent.name == "nav":
            return True
        parent = getattr(parent, "parent", None)
        depth += 1
    return False
