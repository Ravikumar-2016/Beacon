# Corroboration Guidelines

## Purpose

Guidelines for assessing whether key claims on a website are supported by independent external sources.

## Methodology

### 1. Identify Claims Worth Corroborating
Focus on high-impact claims (see F6 in freshness-checklist.md):
- Organization identity and existence.
- Core services/products.
- Location and contact information.
- Significant qualitative claims (awards, certifications, partnerships).

### 2. Source Discovery
Use publicly available methods:
- Web search for the organization name + key identifiers.
- Check for `sameAs` links in structured data (LinkedIn, Wikipedia, social profiles).
- Look for mentions in established directories or registries.
- Search for press mentions or industry references.

### 3. Source Tier Assessment

| Tier | Description | Examples | Confidence |
|---|---|---|---|
| **Tier 1** | Official / authoritative | Government registries, regulatory bodies, .gov/.edu sources, official standards bodies | High |
| **Tier 2** | Established / reputable | Major news outlets, industry associations, established business directories (LinkedIn, Crunchbase), Wikipedia | Medium |
| **Tier 3** | Unverified / low-authority | Personal blogs, scraped directories, unknown aggregators, social media posts | Low |

### 4. Interpretation

| Scenario | Interpretation |
|---|---|
| Multiple Tier 1/2 sources confirm claim | Strongly corroborated |
| One Tier 2 source confirms | Moderately corroborated |
| Only the website itself states the claim | Uncorroborated (but not necessarily false) |
| External sources contradict the claim | Potential inconsistency — flag as finding |

### 5. What NOT to Do
- Do NOT treat lack of corroboration as proof of falsity.
- Do NOT depend on a proprietary API (e.g., paid fact-checking service).
- Do NOT try to corroborate every statement — focus on high-impact claims.
- Do NOT access paywalled sources.
- Do NOT assume small/new businesses are suspicious just because they have limited web presence.

## Evidence Format

Good: "Organization claims 'ISO 27001 certified' on /about; no supporting evidence found in public certification registries or independent sources. Recommend adding certification details or linking to verification."

Bad: "Cannot verify company exists." (Too strong a claim from insufficient evidence.)
