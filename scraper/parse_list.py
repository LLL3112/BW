"""Parse a halooglasi search-results page: discover detail-page URLs."""
import logging
import re

from bs4 import BeautifulSoup

from . import config

log = logging.getLogger("bw_scraper.parse_list")

_DETAIL_HREF_RE = re.compile(r"/nekretnine/[^\s\"'?#]+/\d{6,}(?:[/?#]|$)")


def _normalize(href):
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = config.BASE + href
    return href.split("#")[0]


def extract_detail_urls(html):
    """Return a sorted list of unique listing-detail URLs found on a search page."""
    soup = BeautifulSoup(html, "lxml")
    found = set()

    # Primary: known card container from the site's product-list template.
    for a in soup.select(".product-item a[href], article.product-item a[href], .product-list a[href]"):
        href = a.get("href", "")
        if _DETAIL_HREF_RE.search(href) or (href.startswith("/nekretnine/") and href.rstrip("/").rsplit("/", 1)[-1].isdigit()):
            u = _normalize(href)
            if u:
                found.add(u)

    # Fallback: any anchor on the page whose href looks like a detail page
    # (ends in a long numeric ad ID), regardless of which container it's in.
    if not found:
        for a in soup.select("a[href*='/nekretnine/']"):
            href = a.get("href", "")
            if _DETAIL_HREF_RE.search(href):
                u = _normalize(href)
                if u:
                    found.add(u)

    # Last resort: regex over the raw HTML (handles hrefs injected via JS
    # data attributes that BeautifulSoup's anchor selector might miss).
    if not found:
        for m in _DETAIL_HREF_RE.finditer(html):
            u = _normalize(m.group(0).rstrip("/?#"))
            if u:
                found.add(u)

    log.info("Found %d candidate detail URLs on this page", len(found))
    return sorted(found)


def looks_like_no_results(html):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True).lower()
    return "nema oglasa" in text or "0 oglasa" in text or "no results" in text
