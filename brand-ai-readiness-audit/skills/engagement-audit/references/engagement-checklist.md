# Engagement Checklist

Detailed rules for each engagement-audit detector. All checks are from the perspective of a visitor arriving from an AI referral.

---

## E1 — Landing-Page Orientation

**Check whether the visitor can immediately understand:**
- What this page is about.
- Who the organization is.
- What product/service is being discussed.
- What the page's purpose is.

**Signals:**
- Clear H1 that describes the page topic.
- Organization name visible (logo, header, title).
- Introductory text explaining the page content.
- Breadcrumbs or contextual navigation.

**Flag when:** A visitor landing directly on the page would struggle to understand what they're looking at.

---

## E2 — Clear Next Action

**Check for meaningful CTAs:**
- Get Started, Sign Up, View Products, Book Demo, Compare Plans, Contact Sales, Documentation, Download, etc.

**Do NOT require:** CTAs on every page. Blog posts, about pages, and informational content may not need explicit CTAs.

**Flag when:** Key landing pages (product, service, pricing) lack any clear next step for the visitor.

---

## E3 — Context Retention

**Note:** E3 is not implemented as an independent check: a static audit has no access to the actual referral query that brought a visitor to the page. E4's URL-implied-topic check is the closest deterministically measurable proxy and covers it to the extent possible. The considerations below describe what E3 would assess if that context were available.

**Check whether AI referral context is preserved:**
- If a user asks an AI about "product X pricing" and is sent to `/pricing`, does the pricing page actually show pricing for product X?
- Is the relevant product/service context maintained on the page?
- Can the visitor understand the connection between their query and this page?

**Flag when:** The page content does not support the context that would have brought a visitor here.

---

## E4 — Landing-Page Relevance

**Check:**
- Does the URL path imply specific content?
- Does the page deliver that content?

**Examples:**
- `/product/analytics` should show Analytics product info, not redirect to homepage.
- `/pricing` should show pricing, not a generic "Contact us" page.
- `/careers` should show job listings, not a generic company page.

**Flag when:** URL implies specific content that the page does not deliver — especially if redirects lose context.

---

## E5 — Information Findability

**Check whether important information is reasonably discoverable:**
- Pricing → linked from navigation or product pages.
- Products/services → accessible from homepage or main navigation.
- Contact → findable within 2 clicks.
- Documentation → linked from product pages.
- Support → reasonably discoverable.
- About → accessible from main navigation or footer.

**Do NOT require:** Search functionality on every website. Small sites may not need it.

**Flag when:** Important information is unreasonably difficult to find — buried, unlinked, or requiring many clicks.

---

## E6 — Navigation Clarity

**Check:**
- Are main navigation labels descriptive and unambiguous?
- Can a visitor understand what each nav item leads to?
- Are important categories present in navigation?

**Flag when:** Navigation labels are genuinely ambiguous (e.g., "Solutions" with no indication of what solutions) AND this materially affects finding important information.

**Do NOT:** Perform subjective design criticism. Only flag functional ambiguity.

---

## E7 — Content Hierarchy

**Check whether the page follows a logical flow:**
1. What is this? (clear identification)
2. Why does it matter? (value proposition)
3. What does it offer? (features/products/services)
4. How does it work? (details/process)
5. What should I do next? (next step/CTA)

**Assess using:** Headings, sections, lists, meaningful text.

**Flag when:** The page structure makes it genuinely difficult to understand the offering — not just because it deviates from an ideal template.

---

## E8 — CTA Quality

**Compare:**
- Generic: "Click Here", "Submit", "Learn More", "Read More"
- Specific: "View Enterprise Pricing", "Start Free Trial", "Download SDK", "Book a Demo"

**Flag when:** Important conversion pages use only generic CTAs where specific ones would materially improve clarity.

**Do NOT flag:** Every instance of "Learn More" — sometimes it's appropriate for secondary links.

---

## E9 — Dead Ends

**Check:** Does the page offer a sensible continuation path?
- Links to related content.
- Navigation to other sections.
- CTAs for next steps.
- Footer links.

**Flag when:** Important pages have NO continuation path — the visitor is stuck.

**Do NOT require:** Multiple CTAs. A single clear next step is sufficient.

---

## E10 — Broken Engagement Elements

**Check:**
- Internal links → do they resolve (2xx)?
- CTAs → do they lead to valid destinations?
- Forms → are they accessible (not hidden behind JS failures)?
- Buttons → do they have meaningful destinations?

**Flag when:** Important engagement elements are broken — visitors clicking CTAs hit 404s, forms don't load, etc.

---

## E11 — Mobile/Viewport Usability

**Test viewports:**
- Desktop: 1366×768
- Mobile: 390×844

**Check for major functional problems:**
- Horizontal overflow requiring scrolling.
- Content clipped or hidden.
- Navigation inaccessible on mobile.
- CTAs not visible or tappable on mobile.
- Critical content blocked or overlapping.

**Do NOT judge:** Subjective visual design, color choices, font sizes, or aesthetic preferences.

---

## E12 — Intrusive Interruption

**Detect:**
- Full-screen popups appearing immediately or within a few seconds.
- Mandatory signup/login walls blocking content.
- Cookie banners that block the entire page (not just a small bar).
- Newsletter modals that prevent reading.
- Interstitials that block page interaction.

**Flag when:** The interruption materially blocks access to the page content.

**Do NOT flag:** Small non-blocking notifications, cookie consent bars that allow dismissal, or optional signup prompts that don't block content.

---

## E13 — Trust/Confidence Signals

**Depending on website type, check for:**
- Organization identity (name, about, team).
- Contact information (phone, email, address).
- Product/service details (clear descriptions).
- Pricing information (where expected).
- Support options (help, FAQ, documentation).
- Policies (privacy, terms, returns).
- Credentials (certifications, awards — where relevant).
- Customer evidence (testimonials, case studies — where relevant).

**Do NOT require:** All signals on every site. Assess by website type and context.

**Flag when:** A site type that would typically benefit from trust signals has notably few, AND this would likely affect visitor confidence.
