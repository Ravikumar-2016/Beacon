"""
Render — Headless browser rendering and raw-vs-rendered comparison.

Uses Playwright (if available) to:
- Render pages with JavaScript execution.
- Compare raw HTML text against rendered DOM text.
- Detect content that only appears after JS rendering.
- Gracefully fall back if Playwright is unavailable.
"""

from typing import Any
import logging

logger = logging.getLogger(__name__)

def is_playwright_available() -> bool:
    """Check if Playwright is installed and usable."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False

def render_page(url: str, timeout_ms: int = 15000) -> dict[str, Any]:
    """Render a page using Playwright and extract rendered content.

    Args:
        url: The page URL to render.
        timeout_ms: Maximum time to wait for page load.

    Returns:
        Dictionary with rendered text, headings, links, and metadata.
        Returns None-filled result if Playwright is unavailable.
    """
    result: dict[str, Any] = {
        "url": url,
        "rendered_text": None,
        "rendered_text_length": None,
        "rendered_headings": {},
        "rendered_links": [],
        "rendered_jsonld_count": 0,
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
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768}
                )
                try:
                    page = context.new_page()
                    page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                    
                    # Extract full visible text
                    rendered_text = page.evaluate("document.body ? document.body.innerText : ''")
                    result["rendered_text"] = rendered_text
                    result["rendered_text_length"] = len(rendered_text) if rendered_text else 0
                    
                    # Extract headings
                    headings = {}
                    for i in range(1, 7):
                        tag = f"h{i}"
                        elements = page.locator(tag).all()
                        headings[tag] = [el.text_content().strip() for el in elements if el.text_content()]
                    result["rendered_headings"] = headings
                    
                    # Extract links
                    links = []
                    link_elements = page.locator("a").all()
                    for el in link_elements:
                        href = el.get_attribute("href")
                        text = el.text_content()
                        if href:
                            links.append({"href": href, "text": text.strip() if text else ""})
                    result["rendered_links"] = links
                    
                    # Extract structured data scripts
                    jsonlds = page.locator("script[type='application/ld+json']").all()
                    result["rendered_jsonld_count"] = len(jsonlds)

                except PlaywrightTimeoutError as e:
                    result["error"] = "timeout_error"
                except Exception as e:
                    result["error"] = f"page_error: {str(e)}"
                finally:
                    context.close()
            except Exception as e:
                result["error"] = f"context_error: {str(e)}"
            finally:
                browser.close()
    except Exception as e:
        result["error"] = f"browser_error: {str(e)}"

    return result

def render_multiple_pages(urls: list[str], timeout_ms: int = 15000) -> list[dict[str, Any]]:
    """Render multiple pages reusing a single browser instance."""
    if not is_playwright_available():
        return [{"url": url, "error": "playwright_not_available", "playwright_available": False} for url in urls]
        
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return [{"url": url, "error": "playwright_import_failed", "playwright_available": False} for url in urls]

    results = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for url in urls:
                    result: dict[str, Any] = {
                        "url": url,
                        "rendered_text": None,
                        "rendered_text_length": None,
                        "rendered_headings": {},
                        "rendered_links": [],
                        "rendered_jsonld_count": 0,
                        "playwright_available": True,
                        "error": None,
                    }
                    try:
                        context = browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            viewport={"width": 1366, "height": 768}
                        )
                        try:
                            page = context.new_page()
                            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                            
                            rendered_text = page.evaluate("document.body ? document.body.innerText : ''")
                            result["rendered_text"] = rendered_text
                            result["rendered_text_length"] = len(rendered_text) if rendered_text else 0
                            
                            headings = {}
                            for i in range(1, 7):
                                tag = f"h{i}"
                                elements = page.locator(tag).all()
                                headings[tag] = [el.text_content().strip() for el in elements if el.text_content()]
                            result["rendered_headings"] = headings
                            
                            links = []
                            link_elements = page.locator("a").all()
                            for el in link_elements:
                                href = el.get_attribute("href")
                                text = el.text_content()
                                if href:
                                    links.append({"href": href, "text": text.strip() if text else ""})
                            result["rendered_links"] = links
                            
                            jsonlds = page.locator("script[type='application/ld+json']").all()
                            result["rendered_jsonld_count"] = len(jsonlds)

                        except PlaywrightTimeoutError as e:
                            result["error"] = "timeout_error"
                        except Exception as e:
                            result["error"] = f"page_error: {str(e)}"
                        finally:
                            context.close()
                    except Exception as e:
                        result["error"] = f"context_error: {str(e)}"
                    results.append(result)
            finally:
                browser.close()
    except Exception as e:
        for url in urls:
            if len(results) < len(urls):
                results.append({"url": url, "error": f"browser_error: {str(e)}", "playwright_available": True})

    return results

def compare_raw_vs_rendered(
    raw_text: str,
    rendered_text: str | None,
    raw_headings: dict[str, list[str]] | None = None,
    rendered_headings: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Compare raw HTML content against rendered DOM content.

    Returns:
        Comparison metrics including content_difference_ratio and
        lists of content present only in rendered version.
    """
    if rendered_text is None:
        return {
            "comparison_available": False,
            "reason": "rendered_text_not_available",
        }

    raw_len = len(raw_text.strip()) if raw_text else 0
    rendered_len = len(rendered_text.strip()) if rendered_text else 0

    if rendered_len == 0:
        ratio = 0.0
    else:
        ratio = 1.0 - (raw_len / rendered_len) if raw_len < rendered_len else 0.0
        
    js_dependent = False
    if raw_len < 200 and rendered_len > 500:
        js_dependent = True

    loading_placeholder_detected = False
    lower_raw = raw_text.lower() if raw_text else ""
    if "loading..." in lower_raw or "please wait" in lower_raw or "spinner" in lower_raw:
        loading_placeholder_detected = True

    headings_only_in_rendered = []
    if raw_headings is not None and rendered_headings is not None:
        for tag, r_headings in rendered_headings.items():
            r_set = set(h.strip().lower() for h in r_headings)
            raw_h_list = raw_headings.get(tag, [])
            raw_set = set(h.strip().lower() for h in raw_h_list)
            for r_h in r_headings:
                if r_h.strip().lower() not in raw_set:
                    headings_only_in_rendered.append(r_h)

    return {
        "comparison_available": True,
        "raw_text_length": raw_len,
        "rendered_text_length": rendered_len,
        "content_difference_ratio": round(ratio, 3),
        "significant_gap": ratio > 0.5,
        "js_dependent": js_dependent,
        "headings_only_in_rendered": headings_only_in_rendered,
        "loading_placeholder_detected": loading_placeholder_detected,
    }
