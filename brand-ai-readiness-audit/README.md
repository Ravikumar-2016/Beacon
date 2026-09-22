# Brand AI-Readiness Audit — Agent Skill Marketplace

> **Adobe University Hackathon 2026 — Round 3**

## Purpose

A reusable, general-purpose Agent Skill Marketplace that allows a general AI agent to audit any arbitrary public website for problems affecting:

1. **AI Discoverability** — whether AI systems can discover, access, understand, extract, and confidently use information from the website.
2. **On-site Engagement** — what happens after an AI assistant sends a visitor to the website; whether the visitor can orient, retain context, find information, and take a useful next action.

The marketplace produces a structured audit report containing evidence-backed findings and prioritized, actionable suggested fixes. It is **read-only** and **recommendation-only** — it never modifies the target website.

## Architecture — Four Skills

```
                    AUDIT ORCHESTRATOR
                       (entrypoint)
                           |
         +-----------------+-----------------+
         |                 |                 |
         v                 v                 v
  CRAWL & RENDER    FRESHNESS &       ENGAGEMENT
      AUDIT         CORROBORATION        AUDIT
```

| Skill | Responsibility |
|---|---|
| **audit-orchestrator** | Entrypoint. Validates target URL, plans the audit scope, invokes the three specialist skills, collects evidence, deduplicates findings, resolves severity, prioritizes actions, and produces the final report. |
| **crawl-render-audit** | Technical discoverability. Checks crawl permissions, HTTP accessibility, rendering gaps, machine-readable content, structured data, metadata, internal link structure, and canonical configuration. |
| **freshness-corroboration** | Trust and facts. Checks brand identity consistency, entity ambiguity risk, internal fact consistency, information freshness, and external corroboration. |
| **engagement-audit** | Visitor experience. Checks landing-page orientation, CTAs, context retention*, navigation clarity, content hierarchy, link health, basic mobile usability, intrusive interruptions, and trust signals. |

\* Context retention is not implemented as an independent check: a static audit has no access to the actual referral query that brought a visitor to the page. The landing-page-relevance check (URL-implied-topic vs. content) is the closest deterministically measurable proxy and covers it to the extent possible.

## Entrypoint

The **audit-orchestrator** skill is the single marketplace entrypoint. All audits are initiated through it. It performs one shared robots/crawl/render pass and invokes the three specialist skills against that same evidence — the target site is never crawled more than once.

## Usage

```bash
pip install -r requirements.txt
python -m playwright install chromium

python skills/audit-orchestrator/scripts/orchestrate.py https://example.com
```

This prints the final JSON audit report to stdout.

## Input

The entrypoint accepts a target website URL:

```json
{
  "site": "https://example.com"
}
```

## Output

A structured audit report. Every finding includes `id`, `title`, `severity`, `evidence`, and `suggested_action` (`summary` + `priority`). When the audit surfaces an evidence-gated improvement opportunity that isn't necessarily a defect, the report additionally includes a `proactive_suggestions` array — same shape, but with a `P`-prefixed `id`, no `severity`, and never counted toward `summary.total_findings` (see [Differentiators](#differentiators) below).

### Example: illustrative audit output from a permitted demonstration site

The following is the report produced by a single, real, unmodified run of this engine against `https://example.com/` — a small, publicly accessible site used only to demonstrate the output format. **This is an example of the generalized audit output, not a site-specific capability**: the engine has no special handling for `example.com`, memorizes nothing about it, and does not guarantee the same findings (or any findings at all) on another website. Running this same code against a different site produces a different report, derived entirely from that site's own crawl/render evidence. Full file: [`examples/sample-report.json`](examples/sample-report.json).

```json
{
  "site": "example.com",
  "audited_at": "2026-09-06T04:59:06+00:00",
  "summary": { "total_findings": 1, "critical": 0, "high": 0, "medium": 1 },
  "findings": [
    {
      "id": "F-001",
      "title": "1 important page(s) are dead ends",
      "severity": "medium",
      "evidence": "1 page(s) have no CTA and no other internal links to continue to:\n- `https://example.com` (homepage)",
      "suggested_action": {
        "summary": "Add at least one link (related content, footer, or CTA) so visitors have a next step.",
        "priority": "medium"
      }
    }
  ],
  "proactive_suggestions": [
    {
      "title": "No sitemap was found",
      "evidence": "No `Sitemap:` directive was found in robots.txt, and no sitemap was found at the default /sitemap.xml location.",
      "suggested_action": {
        "summary": "Add a sitemap.xml (and reference it from robots.txt) so crawlers can discover your site's pages systematically rather than relying only on following links.",
        "priority": "low"
      },
      "id": "P-001"
    }
  ]
}
```

Note the proactive suggestion's `evidence` field: it states exactly what was checked (robots.txt's `Sitemap:` directive **and** the default `/sitemap.xml` location) before anything was recommended. That's what "evidence-gated" means here — not a generic best-practice tip attached to every report regardless of whether it applies.

### Illustrative snippet: verification-oriented remediation

This particular demonstration run happened to produce only one finding, whose remediation is already a complete instruction on its own. Other detectors go a step further and name a concrete verification step. For example (quoted verbatim from the current implementation, **not** part of the `example.com` run above — shown only to illustrate the style of remediation produced when a canonical-tag finding fires):

> "Update the `<link rel=\"canonical\">` element on each affected page to point to that page's own definitive, indexable URL (self-referencing if this page is canonical) instead of the current target, then verify the rendered HTML exposes the corrected canonical and that it resolves with HTTP 200."

The included sample report (`examples/sample-report.json`) is a static demonstration artifact; it does not participate in audit execution or influence detector behavior. Deleting it has no effect on the audit engine.

## Differentiators

- **Evidence-gated proactive suggestions** — the system can surface opportunities that are not necessarily defects, but only when sufficient evidence supports them; these are never counted toward `summary.total_findings` or severity counts.
- **Non-overlapping design** — proactive suggestions are checked against the same underlying signals the corresponding detector already uses (e.g. the sameAs-corroboration suggestion reuses the identical entity-ambiguity assessment the F2 detector relies on), so they don't simply duplicate an existing finding.
- **Verification-oriented remediation** — suggested actions identify concrete remediation steps and, where the evidence permits, explain how to verify the resulting change.
- **Generalized architecture** — designed to operate across arbitrary target websites using evidence collected from the target site itself, not memorized characteristics of any particular domain.

## Safety & Constraints

- **Read-only / recommendation-only** — no website modifications, no form submissions, no purchases, no login attempts.
- **Respects robots.txt** — does not crawl disallowed paths.
- **No authenticated access** — only audits publicly accessible content.
- **Conservative crawling** — bounded page limit (15 pages, depth 3), bounded rendering (3 pages), bounded external checks (5 sameAs links, 20 link-health checks, 2 viewport checks), no concurrency. No rate abuse.
- **No destructive actions** — does not bypass security or perform any harmful operation.
- **Provider-neutral** — does not depend on a proprietary external service to resolve the marketplace.
- **No pretrained model weights** — submission ZIP ≤ 50 MB.

## Runtime

A typical audit completes in under 5 minutes on a standard machine.

## Technology

- Python 3.12 for deterministic audit scripts.
- `httpx` for HTTP, `BeautifulSoup` (`html.parser`) for HTML parsing, `Playwright` for rendering (optional graceful fallback — the audit still runs without it, just skipping render-dependent checks), standard library utilities.
- Minimal dependencies (see `requirements.txt`). No LLM API dependency for deterministic checks.

## Validation

1. `marketplace.json` — valid JSON, exactly 4 skills, exactly 1 entrypoint.
2. Each skill directory contains a valid `SKILL.md` with YAML frontmatter (`name`, `description`).
3. Skill `name` matches its directory name.
4. Scripts import and execute without obvious errors.
5. No hardcoded target websites.
6. Final report follows the required schema.

If `skills-ref` is available:

```bash
skills-ref validate ./skills/audit-orchestrator
skills-ref validate ./skills/crawl-render-audit
skills-ref validate ./skills/freshness-corroboration
skills-ref validate ./skills/engagement-audit
```

## Packaging

The submission is a ZIP of the `brand-ai-readiness-audit/` root directory:

```
brand-ai-readiness-audit/
├── marketplace.json
├── README.md
├── requirements.txt
├── examples/
│   └── sample-report.json      # static demonstration artifact; not read by any production code
└── skills/
    ├── audit-orchestrator/
    ├── crawl-render-audit/
    ├── freshness-corroboration/
    └── engagement-audit/
```
