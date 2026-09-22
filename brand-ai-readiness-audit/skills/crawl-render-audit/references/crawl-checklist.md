# Crawl Checklist

Detailed rules for each crawl-render-audit detector. Each detector produces signals; signals become findings only when they represent genuine discoverability problems with evidence and context.

---

## C1 — Crawl Permission (robots.txt)

**Check:**
- Fetch `/robots.txt`.
- Parse user-agent rules (check `*`, `Googlebot`, `GPTBot`, `ChatGPT-User`, `Bingbot`, `Anthropic`, common AI crawlers).
- Compare disallowed paths against important public URLs (from sitemap, navigation).

**Flag when:** Important public content (products, services, about) is blocked.

**Do NOT flag:** Admin, login, API, internal, or legitimately private paths.

**Evidence format:** "robots.txt disallows `/products/` for user-agent `*`; sitemap contains 42 product URLs under this path."

---

## C2 — HTTP Accessibility

**Check:** For each representative page:
- HTTP status code (2xx, 3xx, 4xx, 5xx).
- Connection errors, timeouts.
- Response time.

**Flag when:** Important public pages return 4xx/5xx, time out, or are unreachable.

**Do NOT flag:** Expected 3xx redirects, admin/login pages, or non-critical pages.

---

## C3 — Redirect Chains

**Check:** Follow redirects and record the chain.

**Flag when:**
- Redirect loops detected.
- Chain length > 3 hops.
- Final destination is an error page.
- Redirect loses important URL context (e.g., `/product/analytics` → homepage).

**Do NOT flag:** Clean single redirects (HTTP→HTTPS, www→non-www, trailing slash normalization).

---

## C4 — Raw vs Rendered HTML

**Check:** Compare raw HTML (initial HTTP response) against rendered DOM (after JS execution):
- Text content length.
- Heading presence and content.
- Key business information (product names, prices, descriptions).
- Navigation links.

**Flag when:** Core content is absent from raw HTML and only appears after rendering — meaning a simple crawler would miss it.

**Do NOT flag:** Minor additions from JS (analytics, UI enhancements, lazy-loaded images). Only flag when the discoverability impact is material.

**Metric:** `content_difference_ratio = 1 - (raw_text_length / rendered_text_length)`. Investigate ratios > 0.5 but use judgment — a high ratio alone is not a finding.

---

## C5 — Machine-Readable Content

**Check:** Identify important business information that exists only in non-text formats:
- Critical text rendered as images (logos with company name are OK; pricing tables as images are not).
- Key data in `<canvas>` elements.
- Information behind interactive widgets with no text fallback.

**Flag when:** Important factual content (prices, product specs, contact info) cannot be extracted as text.

**Do NOT flag:** Normal decorative images, icons, background images, or media content.

---

## C6 — Structured Data Presence

**Check:** Extract JSON-LD, Microdata, and RDFa from each page.
- Count and list schema.org types found.
- Note page type (product, article, organization, FAQ, etc.).

**Flag when:** Structured data is absent AND would be genuinely useful for the page type:
- Product pages → Product/Offer schema.
- Organization pages → Organization schema.
- FAQ pages → FAQPage schema.
- Article pages → Article schema.

**Do NOT flag:** Pages where structured data provides minimal benefit (e.g., simple informational pages, generic blog posts).

---

## C7 — Structured Data Consistency

**Check:** Compare structured data values against visible page content:
- `name` vs visible product/page name.
- `price` / `priceCurrency` vs visible price.
- `availability` vs visible availability.
- `aggregateRating` vs visible rating.
- `description` vs visible description.
- `brand` vs visible brand.

**Flag when:** Structured data contradicts visible content — particularly for business-critical fields like price, availability, and identity.

**Severity guide:**
- Price mismatch → HIGH.
- Name mismatch → MEDIUM-HIGH.
- Minor description difference → LOW or no finding.

---

## C8 — Robots Meta / X-Robots-Tag

**Check:**
- `<meta name="robots" content="...">` in HTML.
- `X-Robots-Tag` HTTP header.
- Look for: `noindex`, `nofollow`, `none`, `nosnippet`, `noarchive`.

**Flag when:** Important public pages have `noindex` or `none` — preventing them from appearing in search/AI results.

**Do NOT flag:** `noarchive` alone, or `noindex` on legitimately non-indexable pages (thank-you pages, internal search results).

---

## C9 — Crawlable Internal Links

**Check:** Build internal link graph from crawled pages.
- Identify pages reachable only through deep link chains.
- Identify orphan pages (in sitemap but not linked internally).
- Check whether important page categories are linked from main navigation.

**Flag when:** Important public pages are effectively disconnected from site navigation — hard or impossible to reach by following links.

**Do NOT flag:** Deep archive pages, paginated content, or legitimately low-priority pages.

---

## C10 — Canonical Consistency

**Check:**
- `<link rel="canonical">` tag.
- Compare canonical URL against current URL.
- Compare against redirect target.
- Check for self-referencing canonicals pointing to wrong URL.

**Flag when:**
- Canonical points to a different, unrelated page.
- Canonical points to a 404.
- Multiple pages canonical to each other (loop).
- Canonical conflicts with redirect chain.

**Do NOT flag:** Clean self-referencing canonicals, www/non-www canonicals, or protocol normalization.

---

## C11 — Page Title / Metadata

**Check:**
- `<title>` tag content.
- `<meta name="description">` content.
- Whether title is meaningful and descriptive.

**Flag when:**
- Important pages have empty, generic, or boilerplate titles (e.g., `<title>Home</title>`, `<title>Untitled</title>`).
- Important pages are missing `<title>` entirely.

**Do NOT flag:** Every missing meta description. Only flag title/metadata issues on important pages where it materially affects discoverability.

---

## C12 — Heading / Document Structure

**Check:**
- H1 presence and content.
- Heading hierarchy (H1 → H2 → H3...).
- Semantic HTML sections (`<main>`, `<article>`, `<section>`, `<nav>`).

**Flag when:** Document structure materially hurts machine understanding:
- No H1 on important pages.
- Multiple conflicting H1s on a single product page.
- No semantic structure on content-heavy pages.

**Do NOT flag:** Minor heading hierarchy gaps (H2 → H4 skip) on non-critical pages, or absence of semantic HTML on simple pages.
