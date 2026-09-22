"""
Structured Data — JSON-LD, Microdata, and RDFa extraction and validation.

Extracts structured data from HTML, validates JSON-LD syntax, and compares
structured data values against visible page content for consistency.
"""

import json
import re
from typing import Any

from bs4 import BeautifulSoup


def extract_all_structured_data(html: str) -> dict[str, Any]:
    """Extract all structured data formats from HTML.

    Returns:
        Dictionary with jsonld, microdata, and rdfa extractions.
    """
    soup = BeautifulSoup(html, "html.parser")
    return {
        "jsonld": extract_jsonld(soup),
        "microdata": extract_microdata(soup),
        "rdfa": extract_rdfa(soup),
    }


def extract_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract and parse JSON-LD blocks.

    Returns:
        List of parsed JSON-LD objects with parse status.
    """
    results = []
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        text = script.string or ""
        entry: dict[str, Any] = {"raw": text.strip(), "parsed": None, "valid": False, "error": None}
        try:
            data = json.loads(text)
            entry["parsed"] = data
            entry["valid"] = True
            # Handle @graph
            if isinstance(data, dict) and "@graph" in data:
                entry["types"] = [
                    item.get("@type", "Unknown")
                    for item in data["@graph"]
                    if isinstance(item, dict)
                ]
            elif isinstance(data, dict):
                entry["types"] = [data.get("@type", "Unknown")]
            elif isinstance(data, list):
                entry["types"] = [
                    item.get("@type", "Unknown")
                    for item in data
                    if isinstance(item, dict)
                ]
        except (json.JSONDecodeError, TypeError) as e:
            entry["error"] = str(e)
        results.append(entry)
    return results


def extract_microdata(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract Microdata items (itemscope/itemtype/itemprop)."""
    items = []
    for element in soup.find_all(attrs={"itemscope": True}):
        item_type = element.get("itemtype", "")
        props = {}
        for prop in element.find_all(attrs={"itemprop": True}):
            name = prop.get("itemprop", "")
            value = prop.get("content") or prop.get_text(strip=True)
            if name:
                props[name] = value
        items.append({"type": item_type, "properties": props})
    return items


def extract_rdfa(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract RDFa annotations (typeof/property)."""
    items = []
    for element in soup.find_all(attrs={"typeof": True}):
        type_of = element.get("typeof", "")
        props = {}
        for prop in element.find_all(attrs={"property": True}):
            name = prop.get("property", "")
            value = prop.get("content") or prop.get_text(strip=True)
            if name:
                props[name] = value
        items.append({"type": type_of, "properties": props})
    return items


def extract_prices_from_text(text: str) -> list[str]:
    """Extract price-like patterns from visible text.
    
    Handles formats like $99.99, ₹79,999, €49.99, USD 100, etc.
    """
    if not text:
        return []
    price_pattern = r'(?:[\$\€\£\¥\₹]|USD|EUR|GBP|INR)\s*\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?|\d{1,3}(?:[,\s]\d{3})+(?:\.\d{2})?|\d+\.\d{2}'
    prices = re.findall(price_pattern, text)
    return [p.strip() for p in prices if p.strip()]


def normalize_price(price_str: str) -> float | None:
    """Convert a price string to a numeric value for comparison.
    
    Returns None if unparseable.
    """
    if not price_str:
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(price_str))
        if cleaned:
            return float(cleaned)
    except Exception:
        pass
    return None


def get_schema_properties(jsonld_entry: Any) -> dict[str, Any]:
    """Extract a flat dict of key properties from a JSON-LD entry."""
    props: dict[str, Any] = {}
    
    if not isinstance(jsonld_entry, dict):
        return props
        
    def _extract(data: dict[str, Any]):
        if "name" in data and "name" not in props:
            props["name"] = data["name"]
        if "description" in data and "description" not in props:
            props["description"] = data["description"]
        if "url" in data and "url" not in props:
            props["url"] = data["url"]
        if "image" in data and "image" not in props:
            props["image"] = data["image"]
        if "datePublished" in data and "datePublished" not in props:
            props["datePublished"] = data["datePublished"]
        if "dateModified" in data and "dateModified" not in props:
            props["dateModified"] = data["dateModified"]
            
        if "offers" in data:
            offers = data["offers"]
            if isinstance(offers, dict):
                if "price" in offers:
                    props["price"] = offers["price"]
                if "priceCurrency" in offers:
                    props["priceCurrency"] = offers["priceCurrency"]
                if "availability" in offers:
                    props["availability"] = offers["availability"]
            elif isinstance(offers, list) and offers:
                if isinstance(offers[0], dict):
                    if "price" in offers[0]:
                        props["price"] = offers[0]["price"]
                    if "priceCurrency" in offers[0]:
                        props["priceCurrency"] = offers[0]["priceCurrency"]
                    if "availability" in offers[0]:
                        props["availability"] = offers[0]["availability"]
                        
        if "brand" in data:
            brand = data["brand"]
            if isinstance(brand, dict) and "name" in brand:
                props["brand"] = brand["name"]
            elif isinstance(brand, str):
                props["brand"] = brand
                
        if "aggregateRating" in data:
            rating = data["aggregateRating"]
            if isinstance(rating, dict) and "ratingValue" in rating:
                props["ratingValue"] = rating["ratingValue"]

        for val in data.values():
            if isinstance(val, dict):
                _extract(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        _extract(item)
                        
    _extract(jsonld_entry)
    return props


def assess_page_schema_need(page_type: str, has_structured_data: bool, schema_types: list[str]) -> dict[str, Any]:
    """Assess if the page needs schema based on its type and existing schemas."""
    ptype = page_type.lower()
    needs_schema = False
    suggested = []
    reason = "Page type does not typically require specialized schema."
    
    if ptype == "product":
        if "Product" not in schema_types:
            needs_schema = True
            suggested = ["Product", "Offer", "AggregateRating", "Review"]
            reason = "E-commerce products strongly benefit from Product schema for rich snippets (price, availability, reviews)."
        else:
            reason = "Product schema is already present."
    elif ptype in ["article", "blog"]:
        if "Article" not in schema_types and "NewsArticle" not in schema_types and "BlogPosting" not in schema_types:
            needs_schema = True
            suggested = ["Article", "BlogPosting"]
            reason = "Articles and blog posts benefit from Article schema to appear in top stories and enrich snippets."
        else:
            reason = "Article/BlogPosting schema is already present."
    elif ptype == "local_business":
        if "LocalBusiness" not in schema_types and "Organization" not in schema_types:
            needs_schema = True
            suggested = ["LocalBusiness"]
            reason = "Local businesses should use LocalBusiness schema for local SEO and map integrations."
        else:
            reason = "LocalBusiness/Organization schema is present."
    elif ptype == "faq":
        if "FAQPage" not in schema_types:
            needs_schema = True
            suggested = ["FAQPage"]
            reason = "FAQ pages can achieve large rich snippets by implementing FAQPage schema."
        else:
            reason = "FAQPage schema is already present."
    elif ptype == "organization":
        if "Organization" not in schema_types:
            needs_schema = True
            suggested = ["Organization"]
            reason = "Homepages and about pages should include Organization schema to establish brand identity."
        else:
            reason = "Organization schema is present."
            
    if not has_structured_data and needs_schema:
        reason += " No structured data was found on the page."

    return {
        "needs_schema": needs_schema,
        "suggested_types": suggested,
        "reason": reason
    }


def check_consistency(
    structured_data: dict[str, Any],
    visible_content: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare structured data values against visible page content.

    Args:
        structured_data: Parsed structured data properties.
        visible_content: Extracted visible text properties (name, price, etc.).

    Returns:
        List of inconsistency signals.
    """
    signals = []
    
    visible_title = visible_content.get("title", "")
    visible_h1s = visible_content.get("h1", [])
    visible_text = visible_content.get("visible_text", "")
    
    visible_prices_str = visible_content.get("prices", [])
    if not visible_prices_str and visible_text:
        visible_prices_str = extract_prices_from_text(visible_text)
        
    visible_prices_num = []
    for p in visible_prices_str:
        num = normalize_price(p)
        if num is not None:
            visible_prices_num.append(num)

    jsonlds = structured_data.get("jsonld", [])
    for jd in jsonlds:
        if not jd.get("valid") or not jd.get("parsed"):
            continue
            
        props = get_schema_properties(jd["parsed"])
        
        s_name = str(props.get("name", "")).strip()
        if s_name:
            match_found = False
            if visible_title and s_name.lower() in visible_title.lower():
                match_found = True
            for h1 in visible_h1s:
                if s_name.lower() in str(h1).lower() or str(h1).lower() in s_name.lower():
                    match_found = True
                    break
            
            if not match_found and visible_text and s_name.lower() not in visible_text.lower():
                signals.append({
                    "field": "name",
                    "structured_value": s_name,
                    "visible_value": f"Title: {visible_title}, H1s: {visible_h1s}",
                    "severity": "medium",
                    "detail": "Structured data 'name' not found in visible title, H1s, or page text."
                })

        s_price = props.get("price")
        if s_price is not None:
            s_price_num = normalize_price(str(s_price))
            if s_price_num is not None and visible_prices_num:
                match_found = False
                for vp in visible_prices_num:
                    if abs(vp - s_price_num) < 0.01 or abs(vp * 100 - s_price_num) < 0.01 or abs(vp - s_price_num * 100) < 0.01:
                        match_found = True
                        break
                
                if not match_found:
                    signals.append({
                        "field": "price",
                        "structured_value": str(s_price),
                        "visible_value": ", ".join(visible_prices_str) if visible_prices_str else "None",
                        "severity": "high",
                        "detail": "Structured data price does not match any visible price on the page."
                    })

        s_avail = props.get("availability")
        if s_avail:
            s_avail_str = str(s_avail).lower()
            if "instock" in s_avail_str:
                if visible_text and "out of stock" in visible_text.lower():
                    signals.append({
                        "field": "availability",
                        "structured_value": str(s_avail),
                        "visible_value": "out of stock",
                        "severity": "high",
                        "detail": "Structured data claims InStock but visible text contains 'out of stock'."
                    })

        s_desc = props.get("description")
        if s_desc:
            s_desc_str = str(s_desc).strip()
            chunk = s_desc_str[:50].lower()
            if visible_text and len(chunk) > 10 and chunk not in visible_text.lower():
                signals.append({
                    "field": "description",
                    "structured_value": s_desc_str[:100] + ("..." if len(s_desc_str) > 100 else ""),
                    "visible_value": "Not found in visible text",
                    "severity": "low",
                    "detail": "Structured data description does not appear to be present in visible text."
                })
                
        s_brand = props.get("brand")
        if s_brand:
            s_brand_str = str(s_brand).strip()
            if visible_text and s_brand_str.lower() not in visible_text.lower():
                signals.append({
                    "field": "brand",
                    "structured_value": s_brand_str,
                    "visible_value": "Not found",
                    "severity": "medium",
                    "detail": "Brand from structured data is not visible in page text."
                })

        s_rating = props.get("ratingValue")
        if s_rating:
            s_rating_str = str(s_rating).strip()
            if visible_text and s_rating_str not in visible_text:
                signals.append({
                    "field": "ratingValue",
                    "structured_value": s_rating_str,
                    "visible_value": "Not found",
                    "severity": "low",
                    "detail": "Rating value from structured data not explicitly found in text."
                })

    return signals
