"""Configuration for the Belgrade Waterfront (Beograd na vodi) Halo Oglasi scraper."""

BASE = "https://www.halooglasi.com"

# Search category paths already scoped to the Beograd na vodi micro-location by
# the site's own URL taxonomy. Sale is split by room-layout the way the site
# itself splits it (halooglasi does not offer a single "all layouts" sale
# listing for this micro-location), rental is a single combined listing.
CATEGORIES = {
    "prodaja": [
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/garsonjera",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/jednosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/jednoiposoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/dvosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/dvoiposoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/trosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/troiposoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/cetvorosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/petosoban-i-veci",
    ],
    "izdavanje": [
        "/nekretnine/izdavanje-stanova/beograd-savski-venac-beograd-na-vodi",
    ],
}

MAX_PAGES_PER_CATEGORY = 40  # safety cap; loop stops earlier when a page has no cards
REQUEST_TIMEOUT = 30

# Belgrade Waterfront is a small micro-location (a few dozen listings total
# across every category), so there is no need to hurry: pace requests slowly
# to avoid tripping rate-based anti-bot rules. A real run confirmed the site
# lets an initial handful of requests through fine and then starts 403-ing
# everything once traffic looks automated/fast — these values (plus jitter
# applied at the call site) are deliberately conservative.
SLEEP_BETWEEN_REQUESTS = 6.0
DETAIL_FETCH_SLEEP = 5.0

# If this many fetches in a row come back blocked, stop the run early rather
# than continuing to hammer a WAF that has already started blocking us —
# better to save partial results than escalate a temporary rate-limit.
MAX_CONSECUTIVE_FAILURES = 6

# Text used to hard-filter listings that leak in from outside Beograd na vodi
# despite the scoped URL (e.g. cross-posted or mis-tagged ads). A listing is
# kept only if one of these appears (case-insensitive) in its address, title
# or description.
BW_INCLUDE_MARKERS = [
    "beograd na vodi",
    "belgrade waterfront",
    "bw marina",
    "kula beograd",
    "savski nasip",
    "đorđa stanojevića",
    "djordja stanojevica",
]

# Known Belgrade Waterfront residential buildings / sub-complexes.
# This list is intentionally editable: the scraper's primary source for a
# listing's building is whatever the listing itself states (a dedicated
# "building/complex" field, or the address); this list is only a secondary
# regex-matching aid for titles/descriptions that name a building without it
# being captured as a structured field. Extend freely as new towers launch.
#
# Populated from real scraped titles (run 30249766457, 556 sale listings) —
# almost every real BW building name follows "BW <Name>" in the title, so
# this list was built from actual "BW X" frequency counts rather than guesses.
KNOWN_BUILDINGS = [
    "Kula Beograd",
    "BW Marina",
    "BW Perla",
    "BW Riviera",
    "BW Kings",
    "BW Victoria",
    "BW Sena",
    "BW Quartet",
    "BW Metropolitan",
    "BW Vista",
    "BW Hudson",
    "BW Iris",
    "BW Garden",
    "BW Lena",
    "BW Eden",
    "BW Nika",
    "BW Simfonija",
    "BW Topaz",
    "BW Terraces",
    "BW Aria",
    "BW Lumia",
    "BW Riva",
    "BW Iskra",
    "BW Thalia",
    "BW Aurora",
    "BW Libera",
    "BW Aqua",
    "BW Scala",
    "Alegra",
    "Marina Towers",
    "Belgrade Tower",
    "Sava Residences",
    "Kula na Vodi",
    "BW Residence",
    "Zapadna kapija Beograda na vodi",
]

# Section / zone labels within BW, used when a listing can't be pinned to a
# specific building but can be pinned to a broader area via its address text.
KNOWN_SECTIONS = [
    "Kula Beograd",
    "BW Marina",
    "Savski nasip",
    "Đorđa Stanojevića",
]

# Phrases indicating the seller is the investor/developer selling off-plan /
# direct, as opposed to a completed resale unit.
OFF_PLAN_MARKERS = [
    "direktna prodaja od investitora",
    "prodaja od investitora",
    "u izgradnji",
    "objekat u izgradnji",
    "useljenje 20",  # "useljenje 2027." etc — future move-in date
    "predviđeno useljenje",
    "faza izgradnje",
    "rok za useljenje",
    "off-plan",
    "off plan",
]
RESALE_MARKERS = [
    "useljivo odmah",
    "useljiv odmah",
    "odmah useljivo",
    "kompletno opremljen",
    "renoviran",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Lives under docs/ so GitHub Pages (source = "/docs") can serve the JSON
# straight to the dashboard with a plain relative fetch("data/...").
DATA_DIR = "docs/data"
