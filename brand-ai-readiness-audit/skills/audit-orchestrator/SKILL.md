---
name: audit-orchestrator
description: >
  Entrypoint skill for the Brand AI-Readiness Audit marketplace. Receives a
  target website URL, coordinates the three specialist audit skills
  (crawl-render-audit, freshness-corroboration, engagement-audit), collects
  their evidence, deduplicates findings, resolves severity consistently,
  prioritizes suggested actions, and produces the final structured audit report.
  Use this skill when you need to audit a public website for AI discoverability
  and on-site engagement problems.
license: MIT
---

# Audit Orchestrator

## When to use

Invoke this skill when a user provides a website URL and requests an AI-readiness audit. This is the **only entrypoint** for the Brand AI-Readiness Audit marketplace.

## Inputs

| Field | Type | Required | Description |
|---|---|---|---|
| `site` | URL string | Yes | The target website to audit (e.g. `https://example.com`). |

## Usage

To run a full audit, invoke `orchestrate.py` directly as a single command:

```bash
python skills/audit-orchestrator/scripts/orchestrate.py <url>
```

This prints the final JSON report to stdout. `orchestrate.py` internally performs **one shared** robots/crawl/render pass and then invokes all three specialist audits (`crawl-render-audit`, `freshness-corroboration`, `engagement-audit`) against that same shared evidence — it already implements the full procedure described below.

**Do not independently invoke the three specialist skills yourself for the same live audit.** They are not designed to be invoked standalone against a fresh URL — each expects a `crawl_result` that has already been produced by a shared crawl (see their own SKILL.md "Inputs" sections). Invoking them separately would cause the target site to be crawled multiple times, which this architecture is specifically designed to avoid. Simply run the command above and use its output.

## Procedure

1. **Validate** the target URL (scheme, reachability).
2. **Establish audit scope** — determine representative pages to audit via sitemap, navigation, and bounded crawl (default max 30–50 pages).
3. **Respect robots.txt** — check crawl permissions before fetching.
4. **Invoke specialist skills** in order, passing crawled page data:
   - `crawl-render-audit` — technical discoverability checks.
   - `freshness-corroboration` — trust, consistency, and freshness checks.
   - `engagement-audit` — visitor experience checks.
5. **Collect evidence** from each specialist skill.
6. **Deduplicate findings** — merge overlapping detections across skills (see `scripts/finding_deduplicator.py`).
7. **Resolve severity** — apply consistent severity guidelines (see `references/severity-guidelines.md`).
8. **Prioritize actions** — rank suggested actions by impact.
9. **Identify proactive opportunities** — beyond the defects found above, ask each specialist skill for evidence-gated improvement opportunities that aren't necessarily problems (e.g. a sitemap that exists but isn't referenced from robots.txt, an Organization identity with no `sameAs` corroboration, time-sensitive content with no freshness metadata, a deep page with no breadcrumb trail). These are non-overlapping with the main findings, capped at 5, and never count toward the severity summary.
10. **Build final report** — assemble the structured JSON report, including `proactive_suggestions` when any exist (see `references/finding-schema.md`).

If a specialist skill fails, log the error and continue with remaining skills. One failure should not destroy the entire audit.

## Output

A JSON audit report conforming to the required schema. When evidence-gated proactive opportunities exist (see step 9), the report additionally includes a `proactive_suggestions` array in the same shape as `findings`, but `P`-prefixed and with no `severity` — it is never counted in `summary`:

```json
{
  "site": "...",
  "audited_at": "...",
  "summary": { "total_findings": N, "critical": N, "high": N, "medium": N },
  "findings": [ { "id": "F-001", "title": "...", "severity": "...", "evidence": "...", "suggested_action": { "summary": "...", "priority": "..." } } ],
  "proactive_suggestions": [ { "id": "P-001", "title": "...", "evidence": "...", "suggested_action": { "summary": "...", "priority": "..." } } ]
}
```

## Guardrails

Strictly read-only. This skill and its sub-skills perform only non-mutating HTTP requests (GET for crawling, rendering, and sameAs verification; HEAD for link-health checks) and read-only browser navigation for rendering. No authenticated areas are accessed, no forms are submitted, and no live data is altered.

## References

- [Audit procedure](references/audit-procedure.md) — detailed step-by-step orchestration procedure.
- [Finding schema](references/finding-schema.md) — required report and finding structure.
- [Severity guidelines](references/severity-guidelines.md) — severity level definitions and examples.

## Scripts

- `scripts/orchestrate.py` — main orchestration logic.
- `scripts/finding_deduplicator.py` — cross-skill finding deduplication.
- `scripts/severity.py` — severity resolution and validation.
- `scripts/report_builder.py` — final report assembly and schema validation.
