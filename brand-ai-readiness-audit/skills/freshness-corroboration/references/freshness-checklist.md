# Freshness Checklist

Detailed rules for each freshness-corroboration detector.

---

## F1 — Brand Identity Consistency

**Extract from:**
- Homepage title, H1, logo alt text.
- About page organization name and description.
- Contact page organization name and address.
- Footer organization name across all pages.
- `Organization` structured data: `name`, `legalName`, `alternateName`, `url`, `sameAs`.
- OpenGraph `og:site_name`.

**Compare:**
- Is the organization name consistent across pages?
- Does the domain match the organization name?
- Does structured data `name` match visible branding?

**Flag when:** There are genuine contradictions (e.g., homepage says "Acme Corp" but structured data says "Beta Inc" — and these are different entities, not just legal name vs brand name).

**Do NOT flag:** Brand name vs legal entity name (e.g., "Google" vs "Alphabet Inc."), abbreviated forms, or minor stylistic variations.

---

## F2 — Entity Ambiguity

**Assess:**
- Is the organization name common or generic?
- Are there other prominent organizations with the same or very similar name?
- Does the website provide sufficient distinguishing signals?

**Useful distinguishing signals:**
- Full organization name (not just initials).
- Location / headquarters.
- Industry description.
- Official domain in `sameAs` or `url`.
- Logo (present, not just favicon).
- Unique product/service descriptions.
- Social media profiles in `sameAs`.

**Flag when:** Limited distinguishing information AND the name is generic enough to cause confusion.

**Evidence format:** "Organization uses the name 'Atlas' with no structured data, no sameAs links, and no industry-specific description — risk of confusion with multiple other entities named 'Atlas'."

**Do NOT claim:** "AI will definitely confuse this company."

---

## F3 — Internal Fact Consistency

**Extract and compare across pages:**
- Product names and descriptions.
- Prices (same product, same currency).
- Availability / stock status.
- Contact details (phone, email, address).
- Opening hours.
- Founding year / company history dates.
- Service descriptions.
- Key specifications.
- Policy details.
- Team members / leadership.

**Flag when:** The same fact is stated differently on different pages in a way that creates genuine contradiction.

**Do NOT flag:** Different products with different prices, context-appropriate variations, or historical vs current information when clearly labeled.

---

## F4 — Freshness

**Assess time-sensitivity:**

| Content type | Time-sensitive? |
|---|---|
| Prices, offers, promotions | Yes |
| Product availability | Yes |
| Event dates | Yes |
| Job listings | Yes |
| Software versions | Yes |
| Current leadership | Moderate |
| Opening hours | Moderate |
| Policies | Moderate |
| Services offered | Moderate |
| Company history | No |
| Mission statement | No |
| Educational content | Usually no |

**Check for:**
- Explicit dates (published, modified, copyright year).
- `dateModified` / `datePublished` in structured data.
- References to past dates as if current ("Join us in 2024!").
- Expired offers/promotions still displayed.
- Outdated product versions.
- "Last updated" indicators.

**Flag when:** Time-sensitive information appears potentially stale AND there is evidence suggesting it may no longer be valid.

**Do NOT flag:** Old content simply because it's old. Historical content, foundational descriptions, and evergreen material are not stale.

---

## F5 — External Corroboration

**Source tiers:**

| Tier | Examples | Weight |
|---|---|---|
| 1 | Government registries, regulators, official institutional sources | High |
| 2 | Established publications, industry organizations, reputable directories | Medium |
| 3 | Random blogs, scraped aggregators, unknown sources | Low |

**What to corroborate (when practical):**
- Organization identity (exists, name, location).
- Key claims (industry, size, services).
- Contact information.

**Important:** Failure to find corroboration is NOT proof of falsity. Report as uncertainty, not as a defect.

**Do NOT:** Depend on a proprietary API. Use publicly available search/sources.

---

## F6 — Important Claim Detection

**Prioritize:**
- What the organization is.
- What it sells / provides.
- Where it operates.
- Prices and availability.
- Key specifications.
- Current offerings.

**Do NOT:** Try to externally verify every sentence. Focus on high-impact, verifiable claims.
