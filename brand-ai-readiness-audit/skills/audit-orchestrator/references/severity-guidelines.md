# Severity Guidelines

## Levels

| Level | When to use | Expected frequency |
|---|---|---|
| **CRITICAL** | Severe identity contradiction, major business-critical factual contradiction, core functionality completely inaccessible | Rare |
| **HIGH** | Important crawl blockage, major rendering gap, conflicting pricing, important stale business info, major entity ambiguity, AI referral losing critical context, critical CTA/link failure | Moderate |
| **MEDIUM** | Weak page orientation, moderate fact inconsistency, important info difficult to find, weak corroboration, moderate navigation/context problem | Common |
| **LOW** | Minor clarity issue, minor metadata issue, minor contextual improvement | Common |

## Core Principle

Severity must depend on **IMPACT**, not merely whether a detector fired.

The same signal at different levels of impact should produce different severities:

| Signal | Low impact | High impact |
|---|---|---|
| Missing JSON-LD | Simple blog post → low/no finding | Product page with pricing → high |
| Redirect | Clean single redirect → no finding | Redirect loop on product page → high |
| Old date | Historical "founded in" date → no finding | Expired promotion still displayed → high |

## Signal → Finding Pipeline

```
SIGNAL (detector fires)
  ↓
CONTEXT (what type of page, what type of content)
  ↓
EVIDENCE (specific, verifiable data)
  ↓
IMPACT (how much does this hurt discoverability or engagement)
  ↓
FINDING (with appropriate severity)
```

A signal that has low or no impact should NOT become a finding.

## Examples

### Critical
- Organization name on homepage contradicts Organization structured data name, and the two names refer to completely different entities.
- Product pricing shows $0 in structured data while visible price is $999 — severe data integrity issue.
- robots.txt blocks the entire site (`Disallow: /`) for all user agents.

### High
- robots.txt blocks `/products/` while sitemap contains 42 product URLs.
- Core product content only appears after JavaScript rendering; raw HTML has 183 characters vs 1,240 rendered.
- Product page shows ₹79,999 but JSON-LD says ₹49,999.
- Main service page returns 404.

### Medium
- About page has `<title>Home</title>` instead of a descriptive title.
- Key product page is not linked from main navigation.
- No structured data on product pages where it would genuinely help.
- Contact phone number differs between footer and contact page.

### Low
- Blog post missing meta description.
- Minor heading hierarchy gap (H1 → H3 skip) on informational page.
- Generic CTA text "Learn More" where a more specific label would help.
