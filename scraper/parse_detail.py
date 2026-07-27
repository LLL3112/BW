"""Parse a halooglasi listing detail page into a rich, structured dict.

The site's markup has changed over time and can't be verified live from this
environment (see README), so extraction is deliberately layered:
  1. structured data (JSON-LD / meta tags) when present,
  2. generic label:value pair scanning (dl/dt/dd, table rows, "Label: Value"
     list items) keyed off a Serbian label dictionary,
  3. regex fallback over the raw page text for the same labels.
Any field that can't be found is left as None rather than raising, so a
partial/changed template degrades gracefully instead of dropping the ad.
"""
import json
import logging
import re

from bs4 import BeautifulSoup

from . import config
from .textutil import clean_text, fold, parse_floor, parse_int, parse_number

log = logging.getLogger("bw_scraper.parse_detail")

# canonical_field -> list of Serbian label substrings (folded: lowercase, no diacritics)
LABEL_MAP = {
    "size_sqm": ["kvadratura", "povrsina", "korisna povrsina", "m2"],
    "rooms_raw": ["broj soba", "sobnost"],
    # Real data confirms halooglasi's bare "Spratnost" field IS the floor
    # descriptor (e.g. "VII/15" = 7th of 15 floors, in Roman numerals), not
    # a separate total-floor-count field — "sprat" kept as an alt phrasing.
    "floor_raw": ["spratnost", "sprat"],
    "total_floors": ["spratnost objekta", "ukupno spratova"],
    "heating": ["grejanje"],
    "year_built": ["godina izgradnje"],
    "condition": ["stanje objekta", "uknjizenost", "stanje nekretnine"],
    "price_per_sqm_raw": ["cena po m2", "cena po kvadratu", "cena/m2"],
    "listing_id_raw": ["sifra oglasa", "id oglasa", "kod oglasa"],
    "published_date_raw": ["datum objave", "objavljen"],
    "updated_date_raw": ["azuriran", "poslednja izmena", "datum azuriranja"],
    "agency_name_raw": ["oglasivac", "agencija"],
    "building_raw": ["naziv zgrade", "stambeni kompleks", "zgrada", "rezidencijalni kompleks"],
    "parking_raw": ["parking"],
    "elevator_raw": ["lift"],
    "terrace_raw": ["terasa"],
    "furnished_raw": ["opremljenost", "namestenost"],
    "registered_raw": ["uknjizen"],
    "municipality_raw": ["opstina"],
    "city_area_raw": ["deo grada", "mesna zajednica"],
}

_ALL_LABEL_SUBSTRINGS = [(field, sub) for field, subs in LABEL_MAP.items() for sub in subs]
# match the longest label substrings first so e.g. "cena po m2" wins over "m2"
_ALL_LABEL_SUBSTRINGS.sort(key=lambda t: -len(t[1]))


def _match_label(label_folded):
    for field, sub in _ALL_LABEL_SUBSTRINGS:
        if sub in label_folded:
            return field
    return None


def extract_label_value_pairs(soup):
    """Scan the page for structured "label: value" pairs regardless of markup style."""
    pairs = {}

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = clean_text(dt.get_text())
            value = clean_text(dd.get_text())
            if label and value:
                pairs.setdefault(label, value)

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) == 2:
            label = clean_text(cells[0].get_text())
            value = clean_text(cells[1].get_text())
            if label and value:
                pairs.setdefault(label, value)

    for li in soup.find_all("li"):
        txt = clean_text(li.get_text(" "))
        if ":" in txt and 2 < len(txt) < 160:
            label, _, value = txt.partition(":")
            label, value = clean_text(label), clean_text(value)
            if label and value:
                pairs.setdefault(label, value)
        else:
            spans = li.find_all(["span", "div"], recursive=True)
            if len(spans) >= 2:
                label = clean_text(spans[0].get_text())
                value = clean_text(spans[1].get_text())
                if label and value and label != value:
                    pairs.setdefault(label, value)

    for el in soup.select("[class*='feature'], [class*='char']"):
        txt = clean_text(el.get_text(" "))
        if ":" in txt and 2 < len(txt) < 160:
            label, _, value = txt.partition(":")
            label, value = clean_text(label), clean_text(value)
            if label and value:
                pairs.setdefault(label, value)

    return pairs


def unswap_value_label_pairs(pairs):
    """Fix a real markup pattern found on halooglasi's stat-chip elements.

    They render as <value><label> in DOM order with the label nested inside
    the value's container (e.g. text "32,06 m2" then "Kvadratura" inside one
    parent), which the generic span-pair scan above picks up backwards: the
    assumed "value" ends up being the bare label word itself, and the
    assumed "label" is that word glued onto the real value with no
    separator ("32,06 m2Kvadratura" -> "Kvadratura"). Detect that exact
    shape and swap it back — confirmed against real scraped output where
    size/rooms/floor all came through reversed this way.
    """
    fixed = {}
    for k, v in pairs.items():
        if _match_label(fold(v)) and k.endswith(v) and len(k) > len(v):
            real_value = clean_text(k[: len(k) - len(v)])
            if real_value:
                fixed.setdefault(v, real_value)
                continue
        fixed.setdefault(k, v)
    return fixed


def map_pairs_to_fields(pairs):
    out = {}
    for label, value in pairs.items():
        field = _match_label(fold(label))
        if field and field not in out:
            out[field] = value
    return out


def extract_json_ld(soup):
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except Exception:  # noqa: BLE001
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") in ("Product", "Offer", "RealEstateListing", "Residence"):
                return item
    return None


def extract_images(soup):
    urls = set()
    for img in soup.select("[class*='gallery'] img, [class*='slider'] img, [class*='photo'] img, picture img"):
        src = img.get("data-src") or img.get("src") or img.get("data-lazy")
        if src and "logo" not in src.lower() and "icon" not in src.lower():
            if src.startswith("//"):
                src = "https:" + src
            urls.add(src)
    for meta in soup.select("meta[property='og:image']"):
        content = meta.get("content")
        if content:
            urls.add(content)
    return sorted(urls)


# Sitewide UI hint text that a naive "[class*='description']" match picked
# up instead of the actual ad text on every single listing in a real run —
# explicitly excluded so a wrong-but-plausible-looking match doesn't win.
_GENERIC_UI_TEXT_MARKERS = [
    "u pretrazi sajta mozete zeljene oglase",
]


def _looks_generic(text):
    tf = fold(text)
    return any(marker in tf for marker in _GENERIC_UI_TEXT_MARKERS)


def extract_description(soup):
    for sel in [
        "[class*='description']", "[class*='opis']", "#TextAreaComment", "[itemprop='description']",
        "[class*='OglasDetail'] [class*='Text']", "[data-testid*='description']",
        ".classified-content [class*='text']", "#oglas-opis",
    ]:
        for el in soup.select(sel):
            text = clean_text(el.get_text(" "))
            if len(text) > 20 and not _looks_generic(text):
                return text
    meta = soup.select_one("meta[name='description']")
    if meta:
        text = clean_text(meta.get("content"))
        if text and not _looks_generic(text):
            return text
    return ""


def extract_title(soup):
    h1 = soup.select_one("h1")
    if h1:
        return clean_text(h1.get_text())
    meta = soup.select_one("meta[property='og:title']")
    return clean_text(meta.get("content")) if meta else ""


def extract_price_raw(soup, full_text):
    for sel in [".central-feature", "[class*='price']", "[itemprop='price']"]:
        el = soup.select_one(sel)
        if el:
            txt = clean_text(el.get_text())
            if "€" in txt or re.search(r"\d", txt):
                return txt
    m = re.search(r"[\d.,]+\s*€", full_text)
    return m.group(0) if m else ""


_AGENCY_LINK_HREF_RE = re.compile(r"/(prodavac|agencije|agencija|kompanija|oglasivac|pumk)/", re.IGNORECASE)


def extract_agency_and_owner(soup, full_text, mapped_agency_raw=None, ld=None):
    """Returns (agency_name, is_owner)."""
    folded = fold(full_text)
    owner_markers = ["vlasnik nekretnine", "oglasivac: vlasnik", "vrsta oglasivaca: vlasnik"]
    is_owner = any(m in folded for m in owner_markers)

    agency_el = soup.select_one(
        "[class*='agency-name'], [class*='oglasivac'] a, .company-name, [class*='seller-name'], "
        "[class*='AgencyName'], [class*='CompanyName'], [class*='advertiser'] a, "
        "[data-testid*='agency'], [data-testid*='seller']"
    )
    agency_name = clean_text(agency_el.get_text()) if agency_el else None

    if not agency_name:
        link = soup.find("a", href=_AGENCY_LINK_HREF_RE)
        if link:
            agency_name = clean_text(link.get_text()) or None

    if not agency_name and ld:
        for key in ("seller", "provider", "author"):
            party = ld.get(key)
            if isinstance(party, dict) and party.get("name"):
                agency_name = clean_text(party["name"])
                break

    logo = soup.select_one("[class*='agency'] img, [class*='oglasivac'] img")
    if logo and not agency_name:
        agency_name = clean_text(logo.get("alt", "")) or None

    if not agency_name and mapped_agency_raw:
        value = clean_text(mapped_agency_raw)
        if fold(value) == "vlasnik":
            is_owner = True
        else:
            agency_name = value

    if not agency_name and not is_owner:
        # No agency name found anywhere and no explicit owner marker: check
        # for a generic "Vlasnik" chip commonly shown for private sellers.
        if re.search(r"\bvlasnik\b", folded):
            is_owner = True

    if agency_name:
        is_owner = False

    return agency_name, is_owner


def _stem(word):
    # Serbian noun/adjective case endings are usually 1-2 trailing letters;
    # dropping the last letter turns a literal-phrase match into something
    # that also catches common declined forms (Kula/Kuli/Kulu/Kule, etc.)
    # without pulling in a full morphological analyzer.
    return word[:-1] if len(word) > 3 else word


def detect_building(title, description, address, structured_building):
    if structured_building:
        return clean_text(structured_building)
    haystack = fold(" ".join(filter(None, [title, description, address])))
    for name in config.KNOWN_BUILDINGS:
        words = fold(name).split()
        stems = [_stem(w) for w in words if len(w) >= 3]
        if stems and all(stem in haystack for stem in stems):
            return name
    return None


def detect_section(address, building):
    if building:
        for name in config.KNOWN_SECTIONS:
            if fold(name) in fold(building):
                return name
    haystack = fold(address or "")
    for name in config.KNOWN_SECTIONS:
        if fold(name) in haystack:
            return name
    return None


def detect_off_plan(full_text):
    folded = fold(full_text)
    off_plan_hits = sum(1 for m in config.OFF_PLAN_MARKERS if fold(m) in folded)
    resale_hits = sum(1 for m in config.RESALE_MARKERS if fold(m) in folded)
    if off_plan_hits and off_plan_hits >= resale_hits:
        return True
    if resale_hits:
        return False
    return None  # unknown — not enough signal


def is_within_bw(full_text):
    folded = fold(full_text)
    return any(fold(marker) in folded for marker in config.BW_INCLUDE_MARKERS)


def extract_listing_id_from_url(url):
    m = re.search(r"/(\d{6,})(?:[/?#]|$)", url)
    return m.group(1) if m else None


def parse_rooms_category(rooms_raw, title):
    # halooglasi's "Broj soba" field is already the bare category number
    # (0.5=studio, 1.0, 1.5, 2.0, ...) once extracted correctly — trust it
    # directly rather than re-deriving from Serbian wording when possible.
    if rooms_raw:
        rr = rooms_raw.strip().replace(",", ".")
        if re.fullmatch(r"\d+(?:\.\d+)?", rr):
            return f"{float(rr):.1f}"

    text = fold((rooms_raw or "") + " " + (title or ""))
    mapping = [
        ("garsonjer", "0.5"),
        ("jednoiposoban", "1.5"),
        ("jednosoban", "1.0"),
        ("dvoiposoban", "2.5"),
        ("dvosoban", "2.0"),
        ("troiposoban", "3.5"),
        ("trosoban", "3.0"),
        ("cetvorosoban", "4.0"),
        ("petosoban", "5.0"),
    ]
    for needle, cat in mapping:
        if needle in text:
            return cat
    m = re.search(r"(\d+(?:\.\d)?)\s*sob", text)
    if m:
        return m.group(1)
    return None


LAYOUT_LABELS = {
    "0.0": "Studio",
    "0.5": "Studio",
    "1.0": "1-Bedroom",
    "1.5": "1.5-Bedroom",
    "2.0": "2-Bedroom",
    "2.5": "2.5-Bedroom",
    "3.0": "3-Bedroom",
    "3.5": "3.5-Bedroom",
    "4.0": "4-Bedroom",
    "5.0": "5+-Bedroom",
}


def parse_detail_page(html, url, ad_type, scraped_at):
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(" ", strip=True)

    pairs = extract_label_value_pairs(soup)
    pairs = unswap_value_label_pairs(pairs)
    mapped = map_pairs_to_fields(pairs)
    ld = extract_json_ld(soup) or {}

    title = extract_title(soup)
    description = extract_description(soup)
    address_el = soup.select_one("[class*='address'], [itemprop='address']")
    address = clean_text(address_el.get_text()) if address_el else mapped.get("municipality_raw", "")

    price_raw = extract_price_raw(soup, full_text)
    price_eur = parse_number(price_raw)
    if ld.get("offers", {}).get("price") if isinstance(ld.get("offers"), dict) else ld.get("price"):
        ld_price = ld.get("offers", {}).get("price") if isinstance(ld.get("offers"), dict) else ld.get("price")
        price_eur = price_eur or parse_number(ld_price)

    size_sqm = parse_number(mapped.get("size_sqm"))
    floor_numeric, total_floors_from_floor = parse_floor(mapped.get("floor_raw"))
    total_floors = parse_int(mapped.get("total_floors")) or total_floors_from_floor

    price_per_sqm_raw = mapped.get("price_per_sqm_raw")
    price_per_sqm = parse_number(price_per_sqm_raw)
    if not price_per_sqm and price_eur and size_sqm:
        price_per_sqm = round(price_eur / size_sqm, 2)

    agency_name, is_owner = extract_agency_and_owner(soup, full_text, mapped.get("agency_name_raw"), ld)
    building = detect_building(title, description, address, mapped.get("building_raw"))
    section = detect_section(address, building)
    off_plan = detect_off_plan(full_text)
    rooms_category = parse_rooms_category(mapped.get("rooms_raw"), title)

    listing_id = mapped.get("listing_id_raw") or extract_listing_id_from_url(url)

    record = {
        "listing_id": listing_id,
        "url": url,
        "source": "halooglasi",
        "ad_type": ad_type,
        "title": title,
        "description": description,
        "price_raw": price_raw,
        "price_eur": price_eur,
        "price_per_sqm_raw": price_per_sqm_raw,
        "price_per_sqm_eur": price_per_sqm,
        "rent_monthly_eur": price_eur if ad_type == "izdavanje" else None,
        "size_sqm": size_sqm,
        "rooms_raw": mapped.get("rooms_raw"),
        "rooms_category": rooms_category,
        "layout_group": LAYOUT_LABELS.get(rooms_category),
        "floor_raw": mapped.get("floor_raw"),
        "floor_numeric": floor_numeric,
        "total_floors": total_floors,
        "address": address,
        "municipality": mapped.get("municipality_raw") or "Savski venac",
        "building": building,
        "section": section,
        "heating": mapped.get("heating"),
        "year_built": parse_int(mapped.get("year_built")),
        "condition": mapped.get("condition"),
        "parking": mapped.get("parking_raw"),
        "elevator": mapped.get("elevator_raw"),
        "terrace": mapped.get("terrace_raw"),
        "furnished": mapped.get("furnished_raw"),
        "registered": mapped.get("registered_raw"),
        "agency_name": agency_name,
        "is_owner": is_owner,
        "off_plan": off_plan,
        "published_date_raw": mapped.get("published_date_raw"),
        "updated_date_raw": mapped.get("updated_date_raw"),
        "images": extract_images(soup),
        "scraped_at": scraped_at,
        "in_bw_confirmed": is_within_bw(full_text),
        "extra_features": {k: v for k, v in pairs.items() if fold(k) not in {s for _, subs in LABEL_MAP.items() for s in subs}},
    }
    record["image_count"] = len(record["images"])
    return record
