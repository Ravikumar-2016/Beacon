"""
Viewport Check — Basic mobile/desktop rendering comparison.

Uses a lightweight browser check (Playwright, if available) to detect major
functional problems at key viewport sizes:
- Desktop: 1366x768
- Mobile: 390x844

Only structural/functional problems are checked (horizontal overflow,
navigation or CTA present-in-DOM-but-not-visible) — no subjective visual
design, color, or font assessment, per references/engagement-checklist.md.
"""

from __future__ import annotations

from typing import Any

DESKTOP_VIEWPORT = {"width": 1366, "height": 768}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

# Small tolerance to avoid flagging trivial scrollbar-width rounding as overflow.
_OVERFLOW_TOLERANCE_PX = 20


def is_playwright_available() -> bool:
    """Check if Playwright is installed and usable."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _check_single_viewport(page, viewport: dict[str, int]) -> dict[str, Any]:
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    client_width = viewport["width"]
    overflow_px = scroll_width - client_width
    horizontal_overflow = overflow_px > _OVERFLOW_TOLERANCE_PX

    nav_visible = None
    nav_loc = page.locator("nav").first
    if nav_loc.count() > 0:
        box = nav_loc.bounding_box()
        nav_visible = bool(box) and box["width"] > 0 and box["height"] > 0

    cta_visible = None
    cta_loc = page.locator("button, a.btn, a[class*='btn'], a[class*='cta'], [role='button']").first
    if cta_loc.count() > 0:
        box = cta_loc.bounding_box()
        cta_visible = bool(box) and box["width"] > 0 and box["height"] > 0

    issues: list[dict[str, Any]] = []
    if horizontal_overflow:
        issues.append({
            "type": "horizontal_overflow",
            "detail": f"Page content is {overflow_px}px wider than the {client_width}px viewport.",
        })
    if nav_visible is False:
        issues.append({
            "type": "nav_not_visible",
            "detail": "A <nav> element is present in the DOM but is not visible/rendered at this viewport.",
        })
    if cta_visible is False:
        issues.append({
            "type": "cta_not_visible",
            "detail": "A primary button/CTA element is present in the DOM but is not visible/rendered at this viewport.",
        })

    return {
        "checked": True,
        "issues": issues,
        "scroll_width": scroll_width,
        "viewport_width": client_width,
        "nav_visible": nav_visible,
        "cta_visible": cta_visible,
    }


def check_viewport(url: str, timeout_ms: int = 15000) -> dict[str, Any]:
    """Check page at both desktop and mobile viewports.

    Returns:
        Viewport check results with any major functional problems detected.
        Gracefully reports playwright_available=False (not an error) when
        Playwright is not installed.
    """
    result: dict[str, Any] = {
        "url": url,
        "desktop": {"checked": False, "issues": []},
        "mobile": {"checked": False, "issues": []},
        "playwright_available": False,
        "error": None,
    }

    if not is_playwright_available():
        result["error"] = "playwright_not_available"
        return result

    result["playwright_available"] = True

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        result["error"] = "playwright_import_failed"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for label, viewport in (("desktop", DESKTOP_VIEWPORT), ("mobile", MOBILE_VIEWPORT)):
                    try:
                        context = browser.new_context(
                            viewport=viewport,
                            user_agent="Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0)",
                        )
                        try:
                            page = context.new_page()
                            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                            result[label] = _check_single_viewport(page, viewport)
                        finally:
                            context.close()
                    except PlaywrightTimeoutError:
                        result[label] = {"checked": False, "issues": [], "error": "timeout_error"}
                    except Exception as exc:
                        result[label] = {"checked": False, "issues": [], "error": f"page_error: {exc}"}
            finally:
                browser.close()
    except Exception as exc:
        result["error"] = f"browser_error: {exc}"

    return result


def compare_viewports(
    desktop_result: dict[str, Any],
    mobile_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare desktop and mobile results for major differences.

    Returns:
        List of viewport-specific issues — only fires when something visible
        on desktop disappears on mobile (a stronger signal than either
        viewport's issues alone).
    """
    issues: list[dict[str, Any]] = []
    if desktop_result.get("nav_visible") is True and mobile_result.get("nav_visible") is False:
        issues.append({
            "type": "nav_disappears_on_mobile",
            "detail": "Navigation is visible on desktop but not visible/rendered at the mobile viewport.",
        })
    if desktop_result.get("cta_visible") is True and mobile_result.get("cta_visible") is False:
        issues.append({
            "type": "cta_disappears_on_mobile",
            "detail": "The primary CTA is visible on desktop but not visible/rendered at the mobile viewport.",
        })
    return issues
