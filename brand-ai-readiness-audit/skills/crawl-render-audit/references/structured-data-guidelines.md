# Structured Data Guidelines

## Supported Formats

| Format | Detection method |
|---|---|
| JSON-LD | `<script type="application/ld+json">` tags |
| Microdata | `itemscope`, `itemtype`, `itemprop` attributes |
| RDFa | `typeof`, `property`, `vocab` attributes |

## Extraction

### JSON-LD
1. Find all `<script type="application/ld+json">` tags.
2. Parse JSON content.
3. Handle `@graph` arrays (multiple entities in one block).
4. Extract `@type`, key properties per type.
5. Record parse errors for malformed JSON.

### Microdata
1. Find elements with `itemscope` attribute.
2. Extract `itemtype` (schema.org URL).
3. Extract `itemprop` values from descendants.

### RDFa
1. Find elements with `typeof` attribute.
2. Extract `property` values.

## Schema Types and Expected Contexts

| Page type | Expected schema | Key properties to check |
|---|---|---|
| Product page | `Product`, `Offer` | name, price, priceCurrency, availability, brand, image, description |
| Organization/About | `Organization` | name, url, logo, sameAs, contactPoint, address |
| Article/Blog | `Article`, `BlogPosting` | headline, datePublished, dateModified, author |
| FAQ | `FAQPage`, `Question` | name (question), acceptedAnswer |
| Local business | `LocalBusiness` | name, address, telephone, openingHours, geo |
| Event | `Event` | name, startDate, endDate, location, offers |

## Consistency Checks

Compare structured data values against visible page content for:

| Property | Compare against |
|---|---|
| `name` | Visible product/page title, H1 |
| `price` | Visible price on page |
| `priceCurrency` | Currency symbol/code on page |
| `availability` | Visible availability indicator |
| `aggregateRating.ratingValue` | Visible rating display |
| `brand.name` | Visible brand name |
| `description` | Visible description text |
| `address` | Visible address |
| `telephone` | Visible phone number |

## What NOT to Flag

- Absence of structured data on pages where it provides minimal benefit.
- Minor property differences (e.g., trailing whitespace, slightly different description wording).
- Absence of optional properties (e.g., `image`, `review`).
- Valid structured data using older schema.org versions.
