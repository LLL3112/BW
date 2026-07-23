"""Daily snapshot tracking: new listings per day, and listings removed vs 7 days ago.

Each scraper run writes data/history/seen_<YYYY-MM-DD>.json (overwritten if
the scraper runs more than once on the same day, since the schedule is every
few hours and we only care about one state per calendar day). Diffing
consecutive snapshot files gives new-listing counts; diffing today against
the snapshot from ~7 days ago gives removed listings.
"""
import datetime as dt
import glob
import json
import logging
import os

from . import config

log = logging.getLogger("bw_scraper.history")

HISTORY_DIR = os.path.join(config.DATA_DIR, "history")

_SNAPSHOT_FIELDS = ["listing_id", "title", "price_eur", "size_sqm", "rooms_category",
                     "building", "section", "agency_name", "is_owner", "url", "ad_type"]


def _snapshot_path(date_str):
    return os.path.join(HISTORY_DIR, f"seen_{date_str}.json")


def save_snapshot(date_str, listings):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    slim = [{k: l.get(k) for k in _SNAPSHOT_FIELDS} for l in listings if l.get("listing_id")]
    with open(_snapshot_path(date_str), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=1)
    log.info("Saved snapshot for %s: %d listings", date_str, len(slim))


def _load_snapshot(date_str):
    path = _snapshot_path(date_str)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _all_snapshot_dates():
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "seen_*.json")))
    dates = []
    for f in files:
        base = os.path.basename(f)
        date_str = base[len("seen_"):-len(".json")]
        try:
            dt.date.fromisoformat(date_str)
            dates.append(date_str)
        except ValueError:
            continue
    return sorted(dates)


def _nearest_on_or_before(target_date, available_dates, max_lookback_days=3):
    target = dt.date.fromisoformat(target_date)
    for back in range(0, max_lookback_days + 1):
        candidate = (target - dt.timedelta(days=back)).isoformat()
        if candidate in available_dates:
            return candidate
    return None


def compute_new_and_removed(today_str):
    """Returns dict with new_today (list), removed_vs_7d (list), daily_new_counts (list)."""
    available = _all_snapshot_dates()
    today_snap = _load_snapshot(today_str) or []
    today_ids = {l["listing_id"] for l in today_snap}

    yesterday_str = (dt.date.fromisoformat(today_str) - dt.timedelta(days=1)).isoformat()
    y_date = _nearest_on_or_before(yesterday_str, available)
    y_snap = _load_snapshot(y_date) if y_date else None
    y_ids = {l["listing_id"] for l in y_snap} if y_snap else None
    new_today = [l for l in today_snap if y_ids is not None and l["listing_id"] not in y_ids] if y_ids is not None else []

    week_ago_str = (dt.date.fromisoformat(today_str) - dt.timedelta(days=7)).isoformat()
    w_date = _nearest_on_or_before(week_ago_str, available, max_lookback_days=3)
    w_snap = _load_snapshot(w_date) if w_date else None
    removed_vs_7d = []
    if w_snap is not None:
        removed_vs_7d = [l for l in w_snap if l["listing_id"] not in today_ids]

    daily_new_counts = []
    prev_ids = None
    prev_date = None
    for date_str in available:
        snap = _load_snapshot(date_str) or []
        ids = {l["listing_id"] for l in snap}
        if prev_ids is not None:
            new_count = len(ids - prev_ids)
            removed_count = len(prev_ids - ids)
        else:
            new_count = None
            removed_count = None
        daily_new_counts.append({
            "date": date_str,
            "total_active": len(ids),
            "new_count": new_count,
            "removed_count": removed_count,
        })
        prev_ids, prev_date = ids, date_str

    return {
        "today": today_str,
        "compared_to_yesterday": y_date,
        "compared_to_week_ago": w_date,
        "new_today": new_today,
        "removed_vs_7d": removed_vs_7d,
        "daily_new_counts": daily_new_counts,
    }
