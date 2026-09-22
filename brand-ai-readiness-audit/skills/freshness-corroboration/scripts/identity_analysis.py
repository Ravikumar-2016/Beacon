"""
Identity Analysis — Brand name, domain, and Organization schema extraction.

Extracts identity signals from multiple pages and checks for consistency:
- Organization name across pages.
- Structured data Organization/LocalBusiness entities.
- sameAs links.
- Domain-name alignment.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Corporate suffixes that legitimately vary without indicating a different
# entity (e.g. "Acme" vs "Acme Corp" vs "Acme, Inc."). Stripped before
# comparing names. These are generic corporate-form words, not brand names.
_CORPORATE_SUFFIXES = (
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "group", "gmbh", "plc", "srl", "pvt", "pty",
    "llp", "lp", "sa", "ag", "nv", "bv", "kk",
)

# Common sameAs host patterns that are recognized third-party identity
# platforms (used only to decide whether a broken/redirected sameAs link
# still plausibly points at *some* identity profile, not to validate content).
_KNOWN_SAMEAS_HOSTS = (
    "linkedin.com", "wikipedia.org", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "github.com", "youtube.com", "crunchbase.com",
    "wikidata.org", "pinterest.com", "tiktok.com",
)

# Generic English function words and common section/page-type vocabulary
# ("about", "blog", "works", "team", ...) that show up in identity-adjacent
# text across countless unrelated organizations' sites. Excluded from the
# "shared significant word" check below so that two DIFFERENT organizations
# don't appear compatible merely because both happen to have an "About" or
# "Team" page — this list describes generic page/section vocabulary, not any
# particular organization's name.
_GENERIC_IDENTITY_WORDS = frozenset({
    "the", "and", "of", "in", "on", "at", "to", "for", "a", "an", "is", "are",
    "how", "what", "why", "our", "your", "we", "us",
    "about", "works", "work", "home", "official", "site", "page", "portal",
    "hub", "team", "blog", "news", "help", "support", "contact", "careers",
    "press", "media", "community", "partners",
})


def _significant_tokens(name: str) -> set[str]:
    """Words in a name that could plausibly distinguish one organization
    from another -- normalized, with generic connector/section words and
    short tokens filtered out."""
    normalized = _normalize_name(name)
    return {
        w for w in normalized.split(" ")
        if w and len(w) > 2 and w not in _GENERIC_IDENTITY_WORDS
    }


def _looks_like_identity_candidate(text: str) -> bool:
    """Heuristically decide whether a string plausibly represents an
    organization/brand NAME, as opposed to a tagline, value-proposition
    sentence, question, or other descriptive text.

    Purely structural: real names are short and don't end in
    sentence-terminating punctuation; taglines and descriptive sentences
    commonly do (e.g. "The operating system for D2C telehealth brands.",
    "Why choose us?"). This is a property of the text itself, not of any
    particular website's wording.
    """
    text = (text or "").strip()
    if not text:
        return False
    if text[-1] in ".?":
        return False
    if len(text.split()) > 6:
        return False
    return True


def extract_identity_signals(html: str, url: str = "") -> dict[str, Any]:
    """Extract brand identity signals from a page.

    Args:
        html: Raw HTML content.
        url: Source URL.

    Returns:
        Dictionary of identity signals found on this page.
    """
    soup = BeautifulSoup(html, "html.parser")

    return {
        "url": url,
        "title": _get_title(soup),
        "og_site_name": _get_og(soup, "og:site_name"),
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1")],
        "footer_text": _get_footer_text(soup),
        "logo_alt": _get_logo_alt(soup),
        "organization_schema": _extract_org_schema(html),
    }


def _normalize_name(name: str) -> str:
    """Normalize an organization name for comparison.

    Lowercases, strips punctuation, and removes common corporate-form
    suffixes (Inc, LLC, Corp, ...) so that stylistic/legal-form variants
    of the same name compare as equal.
    """
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r"[.,&/\\'\"()\-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    words = [w for w in n.split(" ") if w and w not in _CORPORATE_SUFFIXES]
    return " ".join(words)


def _names_compatible(a: str, b: str) -> bool:
    """Return True if two (raw) names are plausibly the same entity.

    Compatible when normalized forms are equal, one contains the other
    (handles "Acme" vs "Acme Widgets International"), they share the same
    first significant word (handles minor reordering/truncation), or they
    share any other significant word in common. This last case is what
    makes section/sub-property identity labels compatible with each other:
    different pages of the same site commonly declare section-specific
    identity text ("About Acme", "Acme Developers", "How Acme Works") that
    is never identical and doesn't always share a first word, but does
    share the organization's core token — confirmed necessary by a real
    unseen-site test where a large site's sections each declared their own
    og:site_name. Two genuinely different organizations are very unlikely
    to share any significant word at all, so this stays conservative rather
    than permissive: it doesn't affect Scenario B (a real contradiction like
    "Acme Corporation" vs "Completely Different Corporation" shares no
    token and is still flagged).

    This is intentionally permissive: the goal is to avoid flagging
    legitimate stylistic variation, abbreviations, or brand-vs-legal-name
    differences as contradictions.
    """
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return True  # insufficient evidence either way; don't manufacture a conflict
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    first_a = na.split(" ", 1)[0]
    first_b = nb.split(" ", 1)[0]
    if len(first_a) > 2 and first_a == first_b:
        return True
    if _significant_tokens(a) & _significant_tokens(b):
        return True
    return False


def compare_identity(signals_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare identity signals across multiple pages.

    Deliberately narrow in scope: a schema.org Organization's `name` is
    compared against other declared `name`s and against visible brand
    indicators (og:site_name, homepage H1). `legalName` is NEVER compared
    against visible brand text, because a legal entity name legitimately
    differing from the visible brand (e.g. "Google" / "Alphabet Inc.") is
    expected, not a contradiction.

    Args:
        signals_list: List of identity signal dicts from different pages
            (as returned by extract_identity_signals), each additionally
            carrying a "depth" key (0 = homepage) set by the caller.

    Returns:
        Consistency assessment with any contradictions found.
    """
    # Visible brand-name indicators (each: {"name":..., "source": "<url> (<field>)"})
    visible: list[dict[str, str]] = []
    # Structured-data declared names (schema.org `name`, not `legalName`)
    schema_names: list[dict[str, str]] = []

    for sig in signals_list:
        url = sig.get("url", "")
        if sig.get("og_site_name") and _looks_like_identity_candidate(sig["og_site_name"]):
            visible.append({"name": sig["og_site_name"], "source": f"{url} (og:site_name)"})
        # H1 text is only treated as a brand-name candidate on the homepage.
        # og:site_name and Organization schema `name` are deliberate,
        # site-wide identity declarations wherever they appear, but a page's
        # H1 is just that page's own topic ("Fashion", "Mobiles", "For You")
        # on every page except the homepage — comparing those across pages
        # produces spurious "identity contradictions" on any ordinary
        # multi-page site (confirmed on a real unseen site in Stage 7).
        #
        # Even on the homepage, H1 is not always the brand name: many sites
        # use the H1 for a value-proposition tagline instead (e.g. "The
        # operating system for D2C telehealth brands.") — confirmed as a
        # real false positive on a different unseen site, where that
        # tagline was compared against the site's own consistently-repeated
        # og:site_name as if it were a competing name claim. Only text that
        # structurally looks like a name (short, no sentence-terminating
        # punctuation) is treated as an identity candidate at all.
        if sig.get("depth", 1) == 0:
            h1s = sig.get("h1") or []
            if h1s and _looks_like_identity_candidate(h1s[0]):
                visible.append({"name": h1s[0], "source": f"{url} (H1)"})
        for org in sig.get("organization_schema") or []:
            if org.get("name") and _looks_like_identity_candidate(org["name"]):
                schema_names.append({"name": org["name"], "source": f"{url} (Organization schema name)"})

    contradictions: list[dict[str, Any]] = []

    def _find_conflicts(items: list[dict[str, str]]) -> list[dict[str, Any]]:
        found = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if not _names_compatible(a["name"], b["name"]):
                    found.append({
                        "names": [a["name"], b["name"]],
                        "sources": [a["source"], b["source"]],
                        "detail": f"'{a['name']}' ({a['source']}) is not compatible with '{b['name']}' ({b['source']}).",
                    })
        return found

    # 1. Contradictions among structured-data `name` declarations themselves.
    contradictions += _find_conflicts(schema_names)

    # 2. Contradictions among visible brand indicators themselves.
    contradictions += _find_conflicts(visible)

    # 3. Schema `name` vs visible brand: only a contradiction if NONE of the
    #    schema names is compatible with ANY visible name (i.e. total mismatch,
    #    not just one weak pairing among several).
    if schema_names and visible:
        any_compatible = any(
            _names_compatible(s["name"], v["name"]) for s in schema_names for v in visible
        )
        if not any_compatible:
            contradictions.append({
                "names": [schema_names[0]["name"], visible[0]["name"]],
                "sources": [schema_names[0]["source"], visible[0]["source"]],
                "detail": (
                    f"Structured data declares organization name '{schema_names[0]['name']}' "
                    f"({schema_names[0]['source']}), which does not match any visible brand "
                    f"indicator, e.g. '{visible[0]['name']}' ({visible[0]['source']})."
                ),
            })

    names_found = sorted({item["name"] for item in (visible + schema_names)})

    return {
        "consistent": len(contradictions) == 0,
        "contradictions": contradictions,
        "names_found": names_found,
    }


def assess_entity_ambiguity(signals: dict[str, Any]) -> dict[str, Any]:
    """Assess the risk of entity ambiguity for a single aggregated identity profile.

    Args:
        signals: Aggregated identity profile with keys:
            "name" (best-guess primary name), "name_source" ("schema",
            "og_site_name", "h1", or None), "same_as" (list of URLs),
            "description" (str or None), "has_logo" (bool),
            "address" (str or None).

    Returns:
        Ambiguity risk assessment. Risk is always reported as a *risk*,
        never as a certainty, and small/new businesses are not penalized
        merely for having a limited web presence — risk only rises when
        the name itself is short/generic-shaped AND essentially no
        distinguishing signals are present at all.

        If the only available "name" came from a bare <h1> (no Organization
        schema and no og:site_name — i.e. no deliberate identity
        declaration by the site owner), this is treated as insufficient
        evidence rather than guessed at: an H1 is frequently just a page
        heading ("Welcome", "About Us"), not the organization's name, and
        firing on it would penalize the large fraction of ordinary sites
        that simply don't publish Organization schema.
    """
    name = (signals.get("name") or "").strip()
    name_source = signals.get("name_source")
    same_as = signals.get("same_as") or []
    description = signals.get("description") or ""
    has_logo = bool(signals.get("has_logo"))
    address = signals.get("address") or ""

    if name and name_source == "h1":
        return {
            "risk_level": "unknown",
            "distinguishing_signals": [],
            "concerns": [
                "No explicit identity declaration (Organization schema or og:site_name) found; "
                "only a page heading is available, which is not a reliable identity signal."
            ],
        }

    distinguishing: list[str] = []
    if same_as:
        distinguishing.append(f"{len(same_as)} sameAs link(s)")
    if description and len(description.strip()) >= 20:
        distinguishing.append("organization description")
    if has_logo:
        distinguishing.append("logo present")
    if address:
        distinguishing.append("location/address present")

    word_count = len(name.split()) if name else 0

    if not name:
        # No name signal at all — cannot assess ambiguity meaningfully.
        return {
            "risk_level": "unknown",
            "distinguishing_signals": distinguishing,
            "concerns": ["No organization name signal found to assess."],
        }

    if word_count >= 3:
        risk_level = "low"
    elif len(distinguishing) == 0:
        risk_level = "high" if word_count == 1 else "medium"
    elif len(distinguishing) == 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    concerns: list[str] = []
    if risk_level in ("medium", "high"):
        missing = []
        if not same_as:
            missing.append("no sameAs links")
        if not description or len(description.strip()) < 20:
            missing.append("no organization description")
        if not has_logo:
            missing.append("no logo")
        if not address:
            missing.append("no location/address")
        concerns.append(
            f"Organization uses the name '{name}' with {', '.join(missing)} — "
            f"risk of confusion with other entities using a similar name."
        )

    return {
        "risk_level": risk_level,
        "distinguishing_signals": distinguishing,
        "concerns": concerns,
    }


def _get_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else None


def _get_og(soup: BeautifulSoup, prop: str) -> str | None:
    meta = soup.find("meta", attrs={"property": prop})
    if meta and meta.get("content"):
        return meta.get("content", "").strip()
    return None


def _get_footer_text(soup: BeautifulSoup) -> str | None:
    footer = soup.find("footer")
    if footer:
        return footer.get_text(separator=" ", strip=True)[:500]
    return None


def _get_logo_alt(soup: BeautifulSoup) -> str | None:
    # Common patterns for logo images
    for selector in [
        {"class_": lambda c: c and "logo" in str(c).lower()},
        {"id": lambda i: i and "logo" in str(i).lower()},
        {"alt": lambda a: a and "logo" in str(a).lower()},
    ]:
        img = soup.find("img", attrs=selector)
        if img:
            return img.get("alt", "").strip() or None
    return None


def _extract_org_schema(html: str) -> list[dict[str, Any]]:
    """Extract Organization/LocalBusiness structured data."""
    import json
    soup = BeautifulSoup(html, "html.parser")
    orgs = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data.get("@graph", [data]) if isinstance(data, dict) else data
            for item in items:
                if isinstance(item, dict) and item.get("@type") in (
                    "Organization", "LocalBusiness", "Corporation",
                    "EducationalOrganization", "GovernmentOrganization",
                ):
                    orgs.append({
                        "type": item.get("@type"),
                        "name": item.get("name"),
                        "legal_name": item.get("legalName"),
                        "url": item.get("url"),
                        "same_as": item.get("sameAs", []),
                        "logo": item.get("logo"),
                        "description": item.get("description"),
                        "address": _stringify_address(item.get("address")),
                    })
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return orgs


def _stringify_address(address: Any) -> str | None:
    """Flatten a schema.org PostalAddress (dict or plain string) to text."""
    if not address:
        return None
    if isinstance(address, str):
        return address.strip() or None
    if isinstance(address, dict):
        parts = [
            address.get(k)
            for k in (
                "streetAddress", "addressLocality", "addressRegion",
                "postalCode", "addressCountry",
            )
        ]
        joined = ", ".join(str(p) for p in parts if p)
        return joined or None
    return None


def build_site_identity_profile(
    signals_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate per-page identity signals into a single site-level profile
    suitable for assess_entity_ambiguity().

    Prefers structured-data name over visible brand indicators (an explicit
    schema.org declaration is a stronger identity signal than an H1).
    """
    name = ""
    name_source: str | None = None
    same_as: list[str] = []
    description = ""
    has_logo = False
    address = ""

    for sig in signals_list:
        for org in sig.get("organization_schema") or []:
            if not name and org.get("name"):
                name = org["name"]
                name_source = "schema"
            if org.get("same_as"):
                sa = org["same_as"]
                same_as.extend(sa if isinstance(sa, list) else [sa])
            if not description and org.get("description"):
                description = org["description"]
            if org.get("logo"):
                has_logo = True
            if not address and org.get("address"):
                address = org["address"]
        if not name and sig.get("og_site_name"):
            name = sig["og_site_name"]
            name_source = "og_site_name"
        if sig.get("logo_alt"):
            has_logo = True

    if not name:
        for sig in signals_list:
            h1s = sig.get("h1") or []
            if h1s:
                name = h1s[0]
                name_source = "h1"
                break

    return {
        "name": name,
        "name_source": name_source,
        "same_as": sorted(set(same_as)),
        "description": description,
        "has_logo": has_logo,
        "address": address,
    }
