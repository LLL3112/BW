# BW — Belgrade Waterfront listings dashboard

Tracks every apartment listed for sale (and for rent, as yield comps) in
**Belgrade Waterfront / Beograd na vodi** on halooglasi.com, and publishes an
interactive dashboard from the scraped data. Scraping runs from a
**self-hosted runner** (see below for why); the dashboard is a static site
(no backend) that reads the committed JSON snapshots.

## Live dashboard

GitHub Pages is configured as **Deploy from a branch**, pointed at this
branch's `/docs` folder (Settings → Pages). With that source, GitHub
publishes `docs/` automatically on every push — the `scrape.yml` workflow
just needs to commit updated data there, which it does on each run. Until
the first successful run lands, the dashboard shows an explicit "no data
yet" state rather than fake numbers.

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

## Architecture / why Playwright, and why self-hosted

`scraper/browser.py` fetches pages with headless Chromium (Playwright)
rather than plain `requests`/`cloudscraper`, since a real browser handles
Cloudflare-style JS challenges far better than a plain HTTP client.

That alone wasn't enough, though: the first real run, on a GitHub-hosted
`ubuntu-latest` runner, got an **immediate HTTP 403 with an empty body on
the very first request of every single category** (Actions run
`30047782928`, job `scrape`, ~22:00 UTC 2026-07-23) — not a JS-challenge
page (that would come back as HTTP 200 with a puzzle to solve), a flat
403 at the network edge. That's the signature of a WAF rule blocking
well-known cloud/datacenter IP ranges outright, which also explains why
**every run of the old cloudscraper-based scraper in this repo's history
produced a header-only CSV** going back through the whole git history — it
was never a code bug, it's an IP-reputation block that no amount of
better parsing or a real browser fixes from a datacenter IP.

So `scrape.yml` runs on a **self-hosted runner** instead — the same code,
but from a normal (non-datacenter) IP, same as browsing the site yourself.
See "Self-hosted runner setup" below.

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

## Self-hosted runner setup (Windows, one-time, no admin required)

The workflow is `workflow_dispatch`-only (manual trigger, no cron) — run it
whenever you want fresh data. It needs a self-hosted runner online at that
moment; it doesn't need to run 24/7.

**One-time setup:**
1. On github.com, go to this repo → **Settings → Actions → Runners → New
   self-hosted runner** → choose **Windows / x64**.
2. GitHub shows you exact PowerShell commands with a fresh registration
   token baked in (tokens expire in ~1 hour, so use them promptly rather
   than saving them for later) — copy/paste them into PowerShell one at a
   time. This downloads the runner into a folder like `actions-runner\`
   under wherever you ran the commands (your user folder is fine, no admin
   needed) and registers it against this repo.
3. When `config.cmd` asks for runner name / work folder / labels, defaults
   are fine — just press Enter through the prompts. The workflow targets
   plain `self-hosted`, so no custom label is required.
4. Requires **Git for Windows** to already be installed (it almost
   certainly is if you can already `git clone`/`git push` this repo) —
   the commit step needs Git Bash, which ships with it.

**Each time you want a fresh scrape (~10 minutes, matches the real run
time seen in Actions logs):**
1. Open PowerShell in the `actions-runner` folder, run `.\run.cmd`. It sits
   there listening for a job — leave that window open.
2. On github.com: **Actions → "Scrape Belgrade Waterfront listings" →
   Run workflow** → pick this branch → **Run workflow**.
3. Watch it pick up the job in the PowerShell window. When it finishes
   (commit pushed, Pages will redeploy the dashboard automatically), `Ctrl+C`
   in PowerShell to stop the runner — no need to leave it listening when
   you're not using it.

## Known limitation of this change

This environment's outbound network policy blocks `halooglasi.com` directly
(sandboxed dev container), so the scraper's field extraction could not be
verified against the live site from here — it was validated end-to-end
(crawl → parse → dedup → history → export) against a local fixture server
standing in for halooglasi's HTML, and the dashboard was verified in a real
headless browser against a generated sample dataset. The confirmed-real
issue turned out to be the IP block above, not the parsing logic; the first
self-hosted run is still the real test of the live field-extraction
selectors (`LABEL_MAP` in `scraper/parse_detail.py` is where to add a label
variant if a field comes back empty).

## Running manually

```
pip install -r requirements.txt
playwright install chromium        # omit --with-deps outside Debian/Ubuntu
python scraper.py                  # full run
python scraper.py --max-details 20 # debug: cap detail-page fetches
```
