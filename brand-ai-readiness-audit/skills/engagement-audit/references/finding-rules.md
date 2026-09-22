# Finding Rules

## Signal → Finding Promotion

A detector signal does NOT automatically become a finding. Every signal must pass through:

```
SIGNAL (detector fires)
  ↓
CONTEXT (page type, content type, importance)
  ↓
EVIDENCE (specific, verifiable observation)
  ↓
IMPACT (how much does this affect engagement)
  ↓
FINDING (with appropriate severity)
```

## Promotion Criteria

A signal should become a finding when:

1. **It's on an important page** — product, pricing, homepage, service, contact — not a low-priority archive or utility page.
2. **It affects a real visitor** — the issue would materially impact someone arriving from an AI referral.
3. **The evidence is specific** — not just "this check failed" but "this specific element is missing/broken and here's what that means."
4. **The impact is meaningful** — the visitor's ability to understand, navigate, or act is genuinely affected.

## Suppression Criteria

A signal should NOT become a finding when:

1. **It's on a non-critical page** — and the issue is minor.
2. **It's expected for the page type** — e.g., no CTA on a blog post, no pricing on an about page.
3. **The impact is negligible** — e.g., a slightly generic nav label that's still understandable.
4. **It's subjective design criticism** — not a functional problem.

## Deduplication Rules

When the same underlying problem is detected by multiple detectors:
- Keep the finding with the strongest evidence.
- Merge evidence from multiple detectors into a single finding if they describe the same root cause.
- Do NOT report the same problem multiple times with different framing.

## Evidence Quality

Good evidence:
- "Product page at `/product/analytics` has no H1 heading and no introductory text — a visitor cannot immediately identify what product this page describes."
- "CTA button 'Get Started' on `/pricing` links to `/signup` which returns HTTP 404."

Bad evidence:
- "Page has engagement issues." (Too vague.)
- "Missing trust signals." (No specifics.)
- "Navigation could be improved." (Subjective.)
