---
name: engagement-audit
description: >
  Audits the on-site experience after a visitor arrives from an AI referral.
  Checks landing-page orientation, clear next actions, context retention,
  landing-page relevance, information findability, navigation clarity, content
  hierarchy, CTA quality, dead ends, broken engagement elements, basic mobile
  usability, intrusive interruptions, and trust/confidence signals. Use when
  diagnosing why visitors arriving from AI assistants fail to engage or convert.
license: MIT
---

# Engagement Audit

## When to use

Invoke this skill to analyze what happens after a visitor arrives at a website from an AI referral. Typically invoked by the audit-orchestrator, not directly.

## Inputs

A set of representative page URLs and their rendered content, provided by the orchestrator.

**Note:** this is an internal specialist component of the Brand AI-Readiness Audit marketplace. Its execution during a live audit is coordinated by `audit-orchestrator`'s `orchestrate.py`, which performs one shared crawl and passes the resulting evidence here — it is not intended to be invoked standalone against a live URL.

## Procedure

1. Receive the shared crawl result (already-fetched pages) and any raw-vs-rendered comparisons from the orchestrator.
2. Analyze each page's orientation, CTAs, structural signals, interruptions, and trust signals, excluding pages known to be JS-heavy or HTTP-error pages from raw-HTML-only checks.
3. Run each E1–E13 detector deterministically over that evidence (E3 is not independently implemented — see Detector Categories below).
4. Separately, identify any evidence-gated proactive opportunities (e.g. breadcrumb trails) that are not defects.
5. Return the resulting findings, and any proactive opportunities, to the orchestrator.

## Detector Categories

| ID | Category | Summary |
|---|---|---|
| E1 | Landing-page orientation | Can the visitor immediately understand what this page is and who the org is |
| E2 | Clear next action | Presence of meaningful CTAs (Get Started, View Products, Book Demo, etc.) |
| E3 | Context retention* | Whether AI referral context is preserved on the page |
| E4 | Landing-page relevance | Whether destination URL content matches what the URL implies |
| E5 | Information findability | Whether important info (pricing, contact, docs) is reasonably discoverable |
| E6 | Navigation clarity | Whether navigation labels are understandable and unambiguous |
| E7 | Content hierarchy | Whether page follows a logical what → why → how → next-step flow |
| E8 | CTA quality | Whether CTAs are specific and meaningful vs generic ("Click Here") |
| E9 | Dead ends | Important pages with no sensible continuation path |
| E10 | Broken engagement elements | Broken links, CTAs to 404, empty destinations, inaccessible forms |
| E11 | Mobile/viewport usability | Major functional problems at desktop (1366×768) and mobile (390×844) |
| E12 | Intrusive interruption | Full-screen popups, mandatory signup walls, blocking modals |
| E13 | Trust/confidence signals | Organization identity, contact info, pricing, policies, credentials |

\* E3 is not implemented as an independent check: a static audit has no access to the actual referral query that brought a visitor to the page. E4's URL-implied-topic check is the closest deterministically measurable proxy and covers it to the extent possible.

See `references/engagement-checklist.md` for detailed rules.

### Key principles

- Do **not** require CTAs, search boxes, or trust signals on every page — assess by page type and context.
- Do **not** perform subjective design criticism — only flag functional problems that materially affect engagement.
- Focus on problems from the perspective of an **AI-referred visitor** who may land on any specific URL.

## Output

Structured evidence per page including orientation assessment, CTA inventory, navigation analysis, link health, viewport results, and interruption detection.

## References

- [Engagement checklist](references/engagement-checklist.md) — detailed rules for each detector.
- [Page type guidelines](references/page-type-guidelines.md) — expectations by page type (product, blog, about, etc.).
- [Finding rules](references/finding-rules.md) — signal-to-finding promotion criteria.

## Scripts

- `scripts/page_orientation.py` — page identity, purpose, and organization clarity analysis.
- `scripts/navigation_analysis.py` — navigation structure, labels, and coverage analysis.
- `scripts/cta_analysis.py` — CTA detection, quality assessment, and specificity scoring.
- `scripts/link_health.py` — internal/external link validation, broken link detection.
- `scripts/viewport_check.py` — basic mobile/desktop rendering comparison.
- `scripts/engagement_analysis.py` — aggregation of engagement signals into evidence.
