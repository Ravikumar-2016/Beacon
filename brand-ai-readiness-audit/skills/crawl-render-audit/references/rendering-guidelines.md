# Rendering Guidelines

## Purpose

Guidelines for comparing raw HTML against rendered DOM to detect content that is invisible to simple crawlers.

## Methodology

### 1. Raw HTML Analysis
- Fetch the page with a simple HTTP request (no JS execution).
- Extract visible text content (strip tags, scripts, styles).
- Extract headings (H1–H6).
- Extract links.
- Record raw text length.

### 2. Rendered DOM Analysis (requires Playwright or equivalent)
- Load page in headless browser.
- Wait for network idle or DOM stable state.
- Extract visible text content from rendered DOM.
- Extract headings from rendered DOM.
- Extract links from rendered DOM.
- Record rendered text length.

### 3. Comparison
- Compare text lengths: `content_difference_ratio = 1 - (raw_text_length / rendered_text_length)`.
- Compare heading sets: headings present in rendered but absent in raw.
- Compare key content: product names, prices, descriptions present in rendered but absent in raw.
- Compare link counts: significant navigation links added only by JS.

### 4. Interpretation

| Ratio | Interpretation |
|---|---|
| < 0.2 | Minimal JS dependency — unlikely to be a problem |
| 0.2–0.5 | Moderate JS dependency — investigate what content is added |
| 0.5–0.8 | Heavy JS dependency — likely discoverability problem for key content |
| > 0.8 | Almost entirely JS-rendered — strong finding if page contains important content |

**Important:** The ratio alone is not sufficient. Always check WHAT content is missing from raw HTML. A high ratio caused by added UI chrome is different from a high ratio caused by missing product descriptions.

## Graceful Fallback

If Playwright is unavailable:
- Note the limitation in the audit output.
- Skip raw-vs-rendered comparison.
- Continue with all other checks that work on raw HTML alone.
- Do NOT treat unavailability as a finding about the target website.
