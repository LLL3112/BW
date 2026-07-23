# BW — Belgrade Waterfront listings dashboard

Tracks every apartment listed for sale (and for rent, as yield comps) in
**Belgrade Waterfront / Beograd na vodi** on halooglasi.com, and publishes an
interactive dashboard from the scraped data. Scraping runs on a schedule via
GitHub Actions; the dashboard is a static site (no backend) that reads the
committed JSON snapshots.

## Live dashboard

GitHub Pages is configured as **Deploy from a branch**, pointed at this
branch's `/docs` folder (Settings → Pages). With that source, GitHub
publishes `docs/` automatically on every push — the `scrape.yml` workflow
just needs to commit updated data there, which it does on each scheduled
run. Until the first successful scheduled run lands, the dashboard shows an
explicit "no data yet" state rather than fake numbers.

To preview locally:
```
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```
(the dashboard only needs `docs/data/*.json` to exist next to it — those are
written by the scraper, see below)

## What it collects

For every sale and rental listing under Beograd na vodi, the scraper visits
the listing's own detail page (not just the search-result card) and extracts:
title, price, price/m², size, rooms/layout, floor + building floor count,
building/complex name, address, full description, agency name (or "owner"
private-seller status), listing ID, published/updated dates, all photos, plus
heating, year built, condition, parking/elevator/terrace/furnished/registered
status and anything else the page exposes (kept under `extra_features`).

On top of the raw fields it computes, per run:
- **Duplicate detection** — the same physical unit re-listed by multiple
  agencies (same building/section, size within 1.5 m², matching floor, price
  within 6%) is grouped and flagged.
- **Layout grouping** — studio / 1-bedroom / 1.5 / 2 / … derived from the
  Serbian room-count naming (jednosoban, dvoiposoban, …).
- **Owner vs. agency** — private sellers are identified separately.
- **Off-plan vs. resale** — classified from investor/"u izgradnji"/move-in
  language in the listing text.
- **Agency leaderboard per BW section/building** — who has the most active
  listings where.
- **New-today / removed-vs-7-days-ago** — daily snapshots
  (`docs/data/history/seen_<date>.json`) are diffed to track listing churn.

All of this feeds `docs/data/listings_sale_latest.json`,
`listings_rent_latest.json`, `agency_leaderboard.json`, `history_summary.json`
and `meta.json`, which `docs/app.js` reads client-side. `latest.csv` /
`latest.xlsx` are also written for convenience; the dashboard itself can
export the *currently filtered* view as CSV or Excel from the browser.

## Dashboard features

Tabs: **Overview** (KPIs + charts), **Listings** (full sortable/filterable
table with CSV/Excel export), **By Layout** (grouped cards per layout with
median price/€ per m²), **Duplicates** (cross-agency duplicate groups),
**Agencies & Buildings** (leaderboard + listings-by-building chart),
**New/Removed** (daily churn), and **Yield & ROI Calculator**.

Filters cover price, size, €/m², floor, rooms, building, BW section, agency,
owner-vs-agency, off-plan-vs-resale, and duplicates-only — all composable and
shared across the Listings/By Layout/ROI tabs.

### Yield & ROI Calculator

For each sale listing, it finds comparable *rental* listings (same rooms
category, size within an adjustable ±% tolerance, same building when both
sides have one, else same BW section) scraped from the same site, and
estimates:
- Estimated monthly/annual rent (median €/m² of matching rental comps × the
  sale unit's size)
- Gross yield % (annual rent ÷ price)
- Net yield % after adjustable vacancy rate, management fee, annual
  maintenance (% of price), and other fixed annual costs
- ROI % (unlevered, cash-purchase basis — equal to net yield)
- Payback period in years (price ÷ net annual income)

All assumption inputs are editable in the UI and recompute instantly.

## Architecture / why Playwright

`scraper/browser.py` fetches pages with headless Chromium (Playwright)
rather than plain `requests`/`cloudscraper`. halooglasi.com sits behind
Cloudflare bot-protection, and **every previous run of the old scraper in
this repo's history produced a header-only CSV** (see git history of the old
`data/*.csv` files) — strong evidence that a plain HTTP client was being
challenge-blocked from the GitHub Actions IP range. A real browser executing
the challenge JS is far more reliable from a datacenter IP.

`scraper/parse_detail.py` deliberately does **not** hard-code brittle CSS
class names as its only strategy: it layers JSON-LD parsing, generic
label:value pair scanning (`dl/dt/dd`, table rows, "Label: Value" list
items, matched against a Serbian label dictionary), and regex fallbacks, so
a template tweak degrades a field to `null` instead of breaking the whole
scrape. If a field comes back consistently empty after a real run, check the
Action logs (`parse_list`/`parse_detail` log warnings with page snippets) —
the label dictionary in `LABEL_MAP` (`scraper/parse_detail.py`) is the place
to add a new label variant.

```
scraper/
  config.py       BW category URLs, known buildings/sections, off-plan markers
  browser.py      Playwright-backed fetcher (Cloudflare-resilient)
  parse_list.py   search-results page -> detail-page URLs
  parse_detail.py detail page -> full listing record (all fields)
  textutil.py     Serbian number/floor parsing helpers
  enrich.py       cross-listing duplicate detection + agency leaderboard
  history.py      daily snapshots -> new/removed diffing
  export.py       CSV/XLSX writers
  run.py          orchestrates a full run end-to-end
docs/             static dashboard (GitHub Pages source), + docs/data/*.json
```

## Known limitation of this change

This environment's outbound network policy blocks `halooglasi.com` directly
(sandboxed dev container, not GitHub Actions), so the scraper's field
extraction could not be verified against the live site here. It was
validated end-to-end — crawl → parse → dedup → history → export — against a
local fixture server standing in for halooglasi's HTML, and the dashboard
was verified in a real headless browser against a generated sample dataset
(filters, sorting, all charts, dark mode, CSV/Excel export). The first
scheduled run on GitHub Actions (which does have normal internet access) is
the real test of the live selectors; watch its logs if `sale_count`/
`rent_count` in `docs/data/meta.json` come back at 0.

## Running manually

```
pip install -r requirements.txt
playwright install --with-deps chromium
python scraper.py                  # full run
python scraper.py --max-details 20 # debug: cap detail-page fetches
```
