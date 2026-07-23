"""CSV / XLSX export of listing records."""
import csv
import json

FIELD_ORDER = [
    "listing_id", "ad_type", "title", "price_eur", "price_raw", "price_per_sqm_eur",
    "rent_monthly_eur", "size_sqm", "rooms_raw", "rooms_category", "layout_group",
    "floor_raw", "floor_numeric", "total_floors", "building", "section", "address",
    "municipality", "agency_name", "is_owner", "off_plan", "condition", "heating",
    "year_built", "parking", "elevator", "terrace", "furnished", "registered",
    "is_duplicate", "duplicate_count", "duplicate_group_id", "duplicate_agencies",
    "published_date_raw", "updated_date_raw", "scraped_at", "image_count", "url",
    "description",
]


def _flatten(record):
    row = {}
    for k in FIELD_ORDER:
        v = record.get(k)
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        row[k] = v
    return row


def write_csv(path, listings):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_ORDER)
        writer.writeheader()
        for l in listings:
            writer.writerow(_flatten(l))


def write_xlsx(path, listings):
    try:
        from openpyxl import Workbook
    except ImportError:
        return False
    wb = Workbook()
    ws = wb.active
    ws.title = "Listings"
    ws.append(FIELD_ORDER)
    for l in listings:
        row = _flatten(l)
        ws.append([row.get(k) for k in FIELD_ORDER])
    wb.save(path)
    return True
