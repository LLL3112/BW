"""Orchestrates a full scrape run: crawl -> parse -> enrich -> persist -> export."""
import argparse
import datetime as dt
import json
import logging
import os

from . import config, enrich, export, history
from .browser import BrowserFetcher
from .parse_detail import parse_detail_page
from .parse_list import extract_detail_urls

log = logging.getLogger("bw_scraper.run")


def crawl_category(fetcher, path, ad_type):
    urls = set()
    page = 1
    while page <= config.MAX_PAGES_PER_CATEGORY:
        url = f"{config.BASE}{path}?page={page}"
        html, status = fetcher.get_html(url, wait_selector=".product-item, [class*='product-list']")
        found = extract_detail_urls(html)
        log.info("[%s] page %d -> HTTP %s, %d links", path, page, status, len(found))
        if not found:
            if page == 1:
                log.warning("No listing links found on first page of %s — dumping a snippet for debugging", path)
                log.warning(html[:1500].replace("\n", " "))
            break
        new_links = set(found) - urls
        if not new_links and page > 1:
            # pagination param likely ignored / looped back to page 1 content
            log.info("[%s] page %d had no new links — stopping pagination", path, page)
            break
        urls |= new_links
        page += 1
    return urls


def scrape_all(max_details=None):
    scraped_at = dt.datetime.now(dt.timezone.utc).isoformat()
    all_detail_urls = {}  # url -> ad_type

    with BrowserFetcher() as fetcher:
        for ad_type, paths in config.CATEGORIES.items():
            for path in paths:
                log.info("Crawling category %s (%s)", path, ad_type)
                urls = crawl_category(fetcher, path, ad_type)
                for u in urls:
                    all_detail_urls[u] = ad_type

        log.info("Total unique detail URLs to fetch: %d", len(all_detail_urls))
        items = list(all_detail_urls.items())
        if max_details:
            items = items[:max_details]

        listings = []
        for i, (url, ad_type) in enumerate(items, 1):
            try:
                html, status = fetcher.get_html(url, wait_selector="h1")
                if status and status >= 400:
                    log.warning("Skipping %s (HTTP %s)", url, status)
                    continue
                record = parse_detail_page(html, url, ad_type, scraped_at)
                listings.append(record)
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to parse %s: %s", url, exc)
            if i % 10 == 0:
                log.info("Parsed %d/%d detail pages", i, len(items))

    return listings


def filter_to_bw(listings):
    kept, dropped = [], 0
    for l in listings:
        if l.get("in_bw_confirmed") or l.get("building") or l.get("section"):
            kept.append(l)
        else:
            dropped += 1
    log.info("Kept %d listings confirmed within Beograd na vodi, dropped %d without a BW marker", len(kept), dropped)
    return kept


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-details", type=int, default=None, help="cap number of detail pages fetched (debug)")
    args = parser.parse_args()

    os.makedirs(config.DATA_DIR, exist_ok=True)
    today = dt.date.today().isoformat()

    listings = scrape_all(max_details=args.max_details)
    listings = filter_to_bw(listings)

    enrich.detect_duplicates(listings)
    leaderboard = enrich.agency_leaderboard_by_section(listings)

    sale = [l for l in listings if l["ad_type"] == "prodaja"]
    rent = [l for l in listings if l["ad_type"] == "izdavanje"]

    def dump(name, data):
        with open(os.path.join(config.DATA_DIR, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    dump("listings_sale_latest.json", sale)
    dump(f"listings_sale_{today}.json", sale)
    dump("listings_rent_latest.json", rent)
    dump(f"listings_rent_{today}.json", rent)
    dump("agency_leaderboard.json", leaderboard)

    history.save_snapshot(today, listings)
    hist = history.compute_new_and_removed(today)
    dump("history_summary.json", hist)

    meta = {
        "last_run_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sale_count": len(sale),
        "rent_count": len(rent),
        "duplicate_sale_groups": len({l["duplicate_group_id"] for l in sale if l.get("duplicate_group_id")}),
    }
    dump("meta.json", meta)

    export.write_csv(os.path.join(config.DATA_DIR, "latest.csv"), listings)
    export.write_xlsx(os.path.join(config.DATA_DIR, "latest.xlsx"), listings)

    log.info("Done. sale=%d rent=%d", len(sale), len(rent))


if __name__ == "__main__":
    main()
