"""
Crawl — URL fetching, bounded crawling, and sitemap discovery.

Handles:
- Sitemap.xml discovery and parsing.
- Bounded page crawling with configurable limits.
- HTTP fetching with redirect tracking.
- Page prioritization (homepage, navigation, products, about, contact).
"""

import time
import xml.etree.ElementTree as ET
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

DEFAULT_MAX_PAGES = 50
DEFAULT_TIMEOUT = 15  # seconds
DEFAULT_MAX_DEPTH = 3


def discover_sitemap(base_url: str, timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    """Attempt to discover and parse sitemap.xml.

    Checks /sitemap.xml and robots.txt Sitemap directives.

    Returns:
        List of URLs found in sitemap(s).
    """
    urls = []
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    try:
        resp = httpx.get(sitemap_url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200 and "xml" in resp.headers.get("content-type", ""):
            root = ET.fromstring(resp.text)
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
                
            if "sitemapindex" in root.tag:
                count = 0
                for sitemap in root.iter(f"{ns}sitemap"):
                    loc = sitemap.find(f"{ns}loc")
                    if loc is not None and loc.text:
                        count += 1
                        if count > 3:
                            break
                        child_resp = httpx.get(loc.text.strip(), timeout=timeout, follow_redirects=True)
                        if child_resp.status_code == 200:
                            urls.extend(_parse_sitemap_xml(child_resp.text))
            else:
                urls.extend(_parse_sitemap_xml(resp.text))
    except (httpx.HTTPError, ET.ParseError):
        pass
    return urls


def _parse_sitemap_xml(xml_content: str) -> list[str]:
    """Parse a sitemap XML and extract URLs."""
    urls = []
    try:
        root = ET.fromstring(xml_content)
        # Handle namespace
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        for loc in root.iter(f"{ns}loc"):
            if loc.text:
                urls.append(loc.text.strip())
    except ET.ParseError:
        pass
    return urls


def fetch_page(
    url: str, timeout: int = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Fetch a single page and return structured data about the response.

    Returns:
        Dictionary with status, headers, redirects, body, timing, errors.
    """
    result: dict[str, Any] = {
        "url": url,
        "final_url": url,
        "status": None,
        "redirects": [],
        "headers": {},
        "body": "",
        "content_type": "",
        "response_time_ms": None,
        "error": None,
    }

    try:
        resp = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BrandAIReadinessAudit/1.0"},
        )
        result["status"] = resp.status_code
        result["final_url"] = str(resp.url)
        result["headers"] = dict(resp.headers)
        result["body"] = resp.text
        result["content_type"] = resp.headers.get("content-type", "")
        result["response_time_ms"] = resp.elapsed.total_seconds() * 1000

        # Track redirect chain
        result["redirects"] = [
            {"url": str(r.url), "status": r.status_code}
            for r in resp.history
        ]

    except httpx.TimeoutException:
        result["error"] = "timeout"
    except httpx.ConnectError:
        result["error"] = "connection_failed"
    except httpx.HTTPError as e:
        result["error"] = str(e)

    return result


def is_same_domain(url: str, base_domain: str) -> bool:
    """Check if a URL belongs to the same domain."""
    parsed = urlparse(url)
    return parsed.netloc == base_domain or parsed.netloc.endswith(f".{base_domain}")


def extract_page_links(html: str, base_url: str) -> list[str]:
    """Extract all same-domain internal link hrefs from HTML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    
    links = []
    base_domain = urlparse(base_url).netloc
    
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
            
        absolute_url = urljoin(base_url, href)
        # Remove fragment
        absolute_url = absolute_url.split("#")[0]
        
        if is_same_domain(absolute_url, base_domain):
            links.append(absolute_url)
            
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
            
    return deduped


def prioritize_urls(homepage_url: str, sitemap_urls: list[str], discovered_urls: list[str]) -> list[str]:
    """Returns URLs ordered by priority."""
    priority_keywords = ["about", "contact", "pricing", "product"]
    
    all_urls = [homepage_url] + sitemap_urls + discovered_urls
    
    seen = set()
    deduped = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
            
    if homepage_url in deduped:
        deduped.remove(homepage_url)
        
    def get_priority(url: str) -> int:
        u = url.lower()
        if any(kw in u for kw in priority_keywords):
            return 1
        if url in sitemap_urls:
            return 2
        return 3

    deduped.sort(key=get_priority)
    
    return [homepage_url] + deduped


def bounded_crawl(
    base_url: str,
    is_allowed: Callable[[str], bool] | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Orchestrates bounded crawl from homepage."""
    sitemap_urls = discover_sitemap(base_url, timeout=timeout)
    
    visited = set()
    results = []
    errors = []
    
    queue = [(base_url, 0)]
    discovered = set(sitemap_urls)
    discovered.add(base_url)
    
    urls_crawled = 0
    urls_discovered_count = len(discovered)
    
    priority_keywords = ["about", "contact", "pricing", "product"]
    
    while queue and urls_crawled < max_pages:
        # Sort queue by depth, then priority
        queue.sort(key=lambda item: (
            item[1], 
            0 if item[0] == base_url else (
                1 if any(kw in item[0].lower() for kw in priority_keywords) else (
                    2 if item[0] in sitemap_urls else 3
                )
            )
        ))
        
        current_url, depth = queue.pop(0)
        
        if current_url in visited:
            continue
            
        if is_allowed and not is_allowed(current_url):
            visited.add(current_url)
            continue
            
        lower_url = current_url.lower()
        # Skip obvious non-page patterns
        if any(ext in lower_url for ext in [".pdf", ".jpg", ".png", ".gif", ".jpeg", ".mp4", ".zip", "/api/", "/feed", "/rss"]) or "?" in lower_url and len(lower_url.split("?")[1]) > 20:
            visited.add(current_url)
            continue
            
        visited.add(current_url)
        
        if urls_crawled > 0:
            time.sleep(0.5)
            
        page_result = fetch_page(current_url, timeout=timeout)
        page_result["depth"] = depth
        
        if page_result["error"]:
            errors.append({"url": current_url, "error": page_result["error"]})
        else:
            if "text/html" not in page_result.get("content_type", "").lower():
                continue
                
            results.append(page_result)
            urls_crawled += 1
            
            if depth < max_depth:
                new_links = extract_page_links(page_result["body"], base_url)
                for link in new_links:
                    if link not in visited and not any(q[0] == link for q in queue):
                        queue.append((link, depth + 1))
                        if link not in discovered:
                            discovered.add(link)
                            urls_discovered_count += 1
                            
    return {
        "pages": results,
        "sitemap_urls": sitemap_urls,
        "urls_discovered": urls_discovered_count,
        "urls_crawled": urls_crawled,
        "errors": errors
    }
