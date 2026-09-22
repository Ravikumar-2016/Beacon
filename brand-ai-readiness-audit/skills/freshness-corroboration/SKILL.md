---
name: freshness-corroboration
description: >
  Audits whether important facts on a website are clearly associated with the
  correct entity, internally consistent, appropriately current, and sufficiently
  corroborated. Checks brand identity consistency, entity ambiguity risk,
  internal fact contradictions, information freshness, external corroboration,
  and important claim detection. Use when diagnosing why AI assistants may
  misrepresent, confuse, or distrust a brand's information.
license: MIT
---

# Freshness & Corroboration Audit

## When to use

Invoke this skill to determine whether a website's factual content is consistent, current, clearly attributed to the right entity, and corroborated. Typically invoked by the audit-orchestrator, not directly.

## Inputs

A set of representative page URLs and their parsed content, provided by the orchestrator.

**Note:** this is an internal specialist component of the Brand AI-Readiness Audit marketplace. Its execution during a live audit is coordinated by `audit-orchestrator`'s `orchestrate.py`, which performs one shared crawl and passes the resulting evidence here — it is not intended to be invoked standalone against a live URL.

## Procedure

1. Receive the shared crawl result (already-fetched pages) from the orchestrator.
2. Extract identity signals, facts, and freshness signals from each page's content.
3. Run each F1–F5 detector deterministically over that evidence, including bounded external corroboration checks (sameAs verification, independent-source lookups) where applicable.
4. Separately, identify any evidence-gated proactive opportunities (e.g. sameAs corroboration, freshness metadata) that are not defects.
5. Return the resulting findings, and any proactive opportunities, to the orchestrator.

## Detector Categories

| ID | Category | Summary |
|---|---|---|
| F1 | Brand identity consistency | Contradictions in organization name, domain, branding across pages |
| F2 | Entity ambiguity | Risk of confusion with other organizations sharing a similar name |
| F3 | Internal fact consistency | Contradictory facts (prices, specs, contacts, dates) across pages |
| F4 | Freshness | Time-sensitive information that may be stale |
| F5 | External corroboration | Whether key claims are supported by independent sources |
| F6 | Important claim detection | Prioritizing which claims warrant verification |

See `references/freshness-checklist.md` for detailed rules.

### Key principles

- **F1**: Do not treat brand name vs legal entity as automatically contradictory.
- **F2**: Never claim "AI will definitely confuse this company." Report risk with evidence.
- **F3**: Contradictions must be evidence-backed with specific page references.
- **F4**: Do not flag old information simply because it is old. Assess whether it is time-sensitive and potentially stale.
- **F5**: Failure to find corroboration is NOT proof that a claim is false. Treat as uncertainty.
- **F6**: Focus on high-impact claims (identity, products, prices, services, availability).

## Output

Structured evidence including identity signals, extracted facts with page sources, detected contradictions, freshness assessments, and corroboration results.

## References

- [Freshness checklist](references/freshness-checklist.md) — detailed rules for each detector.
- [Corroboration guidelines](references/corroboration-guidelines.md) — source tier definitions and methodology.

## Scripts

- `scripts/identity_analysis.py` — brand name, domain, Organization schema extraction and comparison.
- `scripts/fact_consistency.py` — cross-page fact extraction and contradiction detection.
- `scripts/freshness_analysis.py` — date extraction, staleness assessment for time-sensitive content.
- `scripts/corroboration.py` — external source lookup and confidence assessment.
