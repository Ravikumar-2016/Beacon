# Audit Procedure

## Step-by-step orchestration

### 1. Input Validation
- Validate URL format (must have scheme: `http://` or `https://`).
- Normalize URL (strip trailing slash, resolve relative).
- Verify the domain is reachable (HEAD request with timeout).

### 2. Scope Planning
- Fetch and parse `robots.txt`.
- Attempt sitemap discovery (`/sitemap.xml`, robots.txt `Sitemap:` directives).
- Crawl homepage and extract main navigation links.
- Build a prioritized URL list:
  1. Homepage
  2. Sitemap URLs (sampled if large)
  3. Main navigation targets
  4. Product/service pages
  5. About/contact pages
  6. Representative content pages
- Apply crawl limits (default: max 30–50 pages, bounded depth).

### 3. Page Fetching
- Fetch each URL respecting robots.txt.
- Record HTTP status, redirects, response headers, response time.
- Parse raw HTML.
- Optionally render with headless browser (Playwright) if available.

### 4. Specialist Invocation
- Pass page data to `crawl-render-audit`.
- Pass page data to `freshness-corroboration`.
- Pass page data to `engagement-audit`.
- Each runs independently. If one fails, log error and continue.

### 5. Evidence Collection
- Collect structured evidence from each specialist.
- Each specialist returns a list of signals with evidence.

### 6. Finding Assembly
- Promote signals to findings using signal → context → evidence → impact → finding pipeline.
- Assign finding IDs sequentially: `F-001`, `F-002`, etc.
- Resolve severity using `severity-guidelines.md`.
- Deduplicate overlapping findings from different skills.

### 7. Report Generation
- Assemble final JSON report per `finding-schema.md`.
- Compute summary counts.
- Sort findings by severity (critical → high → medium → low).
- Sort suggested actions by priority.

### Error Handling
- robots.txt fetch failure → log, assume allow (conservative).
- Page timeout → record timeout evidence, continue.
- Playwright unavailable → skip rendering comparison, note limitation.
- Malformed structured data → record parse error, continue.
- Specialist skill failure → log, continue with remaining skills.
