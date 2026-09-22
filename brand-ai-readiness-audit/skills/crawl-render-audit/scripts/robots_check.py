"""
Robots Check — robots.txt parsing and permission checking.

Handles:
- Fetching and parsing robots.txt.
- Checking if a URL is allowed for specific user agents.
- Extracting Sitemap directives.
- Identifying important paths that are blocked.
"""

from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

# User agents to check (common AI crawlers + standard)
AI_USER_AGENTS = [
    "*",
    "Googlebot",
    "GPTBot",
    "ChatGPT-User",
    "Google-Extended",
    "Bingbot",
    "anthropic-ai",
    "Claude-Web",
    "Bytespider",
    "CCBot",
]


def fetch_robots_txt(base_url: str, timeout: int = 10) -> dict[str, Any]:
    """Fetch and parse robots.txt for the target site.

    Returns:
        Dictionary with raw content, parsed rules, sitemap URLs, and any errors.
    """
    robots_url = urljoin(base_url, "/robots.txt")
    result: dict[str, Any] = {
        "url": robots_url,
        "exists": False,
        "raw_content": "",
        "sitemap_urls": [],
        "parser": None,
        "error": None,
    }

    try:
        resp = httpx.get(robots_url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            result["exists"] = True
            result["raw_content"] = resp.text
            result["sitemap_urls"] = _extract_sitemaps(resp.text)

            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            result["parser"] = parser
        else:
            result["error"] = f"HTTP {resp.status_code}"
    except httpx.HTTPError as e:
        result["error"] = str(e)

    return result


def is_url_allowed(parser: RobotFileParser | None, url: str, user_agent: str = "*") -> bool:
    """Check if a URL is allowed for a given user agent.

    If no parser is available, defaults to allowed (conservative).
    """
    if parser is None:
        return True
    return parser.can_fetch(user_agent, url)


def check_blocked_paths(
    parser: RobotFileParser | None,
    urls: list[str],
    user_agents: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Check which URLs are blocked for which user agents.

    Returns:
        List of blocked path entries with URL, user_agent, and blocked status.
    """
    if parser is None:
        return []

    if user_agents is None:
        user_agents = AI_USER_AGENTS

    blocked = []
    for url in urls:
        for ua in user_agents:
            if not is_url_allowed(parser, url, ua):
                blocked.append({
                    "url": url,
                    "user_agent": ua,
                    "blocked": True,
                })
    return blocked


def _extract_sitemaps(robots_content: str) -> list[str]:
    """Extract Sitemap URLs from robots.txt content."""
    sitemaps = []
    for line in robots_content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            url = stripped[len("sitemap:"):].strip()
            if url:
                sitemaps.append(url)
    return sitemaps
