---
name: crawl-render-audit
description: >
  Audits whether important website content can be reached, fetched, rendered,
  read, and structurally understood by machines. Checks crawl permissions
  (robots.txt), HTTP accessibility, redirect chains, raw-vs-rendered HTML gaps,
  machine-readable content, structured data presence and consistency,
  robots meta/X-Robots-Tag, crawlable internal links, canonical configuration,
  page metadata, and document structure. Use when diagnosing why AI crawlers
  cannot discover or extract content from a website.
license: MIT
---

# Crawl & Render Audit

## When to use

Invoke this skill to determine whether a website's content is technically discoverable and extractable by AI systems and crawlers. Typically invoked by the audit-orchestrator, not directly.

## Inputs

A set of representative page URLs and their fetched content, provided by the orchestrator.

**Note:** this is an internal specialist component of the Brand AI-Readiness Audit marketplace. Its execution during a live audit is coordinated by `audit-orchestrator`'s `orchestrate.py`, which performs one shared crawl and passes the resulting evidence here — it is not intended to be invoked standalone against a live URL.

## Procedure

1. Receive the shared crawl result (pages, sitemap URLs, robots.txt data, and any raw-vs-rendered comparisons) already gathered by the orchestrator.
2. Analyze each page's HTML, metadata, structured data, links, and loading placeholders.
3. Run each C1–C12 detector deterministically over that evidence; a detector produces a finding only when its signal is backed by sufficient contextual evidence.
4. Separately, identify any evidence-gated proactive opportunities (e.g. sitemap referenced from robots.txt) that are not defects.
5. Return the resulting findings, and any proactive opportunities, to the orchestrator.

## Detector Categories

Each detector produces **signals**, not automatic findings. Signals are promoted to findings only when they represent a genuine discoverability problem backed by evidence and context.

| ID | Category | Summary |
|---|---|---|
| C1 | Crawl permission | robots.txt rules blocking important public content |
| C2 | HTTP accessibility | Important pages returning errors or timing out |
| C3 | Redirect chains | Loops, broken redirects, excessively long chains |
| C4 | Raw vs rendered HTML | Core content missing from initial HTML, only appearing after JS rendering |
| C5 | Machine-readable content | Important business info locked in images/canvas/non-text |
| C6 | Structured data presence | Missing JSON-LD/Microdata/RDFa where genuinely useful for the page type |
| C7 | Structured data consistency | Structured data contradicting visible page content |
| C8 | Robots meta / X-Robots-Tag | Indexing directives preventing content from being served |
| C9 | Crawlable internal links | Important pages disconnected from site navigation |
| C10 | Canonical consistency | Suspicious or problematic canonical configurations |
| C11 | Page title / metadata | Important pages with meaningless or missing titles |
| C12 | Heading / document structure | Structure that materially hurts machine understanding |

See `references/crawl-checklist.md` for detailed detector rules.

## Output

Structured evidence per page, including HTTP status, redirects, rendering comparison, structured data extraction, metadata, headings, and internal link data. Findings are evidence-backed with severity assessed by impact.

## References

- [Crawl checklist](references/crawl-checklist.md) — detailed rules for each detector.
- [Rendering guidelines](references/rendering-guidelines.md) — raw vs rendered comparison methodology.
- [Structured data guidelines](references/structured-data-guidelines.md) — schema.org validation rules.

## Scripts

- `scripts/crawl.py` — URL fetching, bounded crawling, sitemap discovery.
- `scripts/robots_check.py` — robots.txt parsing and permission checking.
- `scripts/render.py` — headless browser rendering and comparison.
- `scripts/html_analysis.py` — raw HTML content analysis.
- `scripts/structured_data.py` — JSON-LD/Microdata/RDFa extraction and validation.
- `scripts/link_analysis.py` — internal link graph and connectivity analysis.
- `scripts/metadata_analysis.py` — title, description, canonical, robots meta extraction.
