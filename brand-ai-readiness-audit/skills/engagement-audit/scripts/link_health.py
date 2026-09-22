"""
Link Health — Internal/external link validation and broken link detection.

Validates links found on pages to detect:
- Broken links (4xx/5xx responses).
- CTAs leading to error pages.
- Empty or invalid destinations.
"""

from typing import Any

import httpx


def check_links(
    links: list[dict[str, str]],
    timeout: int = 10,
    max_checks: int = 50,
) -> list[dict[str, Any]]:
    """Check health of a list of links.

    Args:
        links: List of dicts with 'href' and 'text' keys.
        timeout: Request timeout in seconds.
        max_checks: Maximum number of links to check.

    Returns:
        List of link health results.
    """
    results = []
    for link in links[:max_checks]:
        href = link.get("href", "")
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        result: dict[str, Any] = {
            "href": href,
            "text": link.get("text", ""),
            "status": None,
            "error": None,
            "is_broken": False,
        }

        try:
            resp = httpx.head(
                href,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "BrandAIReadinessAudit/1.0"},
            )
            result["status"] = resp.status_code
            result["is_broken"] = resp.status_code >= 400
        except httpx.TimeoutException:
            result["error"] = "timeout"
            result["is_broken"] = True
        except httpx.HTTPError as e:
            result["error"] = str(e)
            result["is_broken"] = True

        results.append(result)

    return results


def find_broken_ctas(
    ctas: list[dict[str, Any]],
    link_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cross-reference CTAs with link health to find broken CTAs.

    Returns:
        List of broken CTA findings.
    """
    broken_urls = {r["href"] for r in link_results if r.get("is_broken")}
    broken_ctas = []
    for cta in ctas:
        href = cta.get("href", "")
        if href in broken_urls:
            broken_ctas.append({
                "cta_text": cta.get("text", ""),
                "href": href,
                "issue": "broken_destination",
            })
    return broken_ctas
