"""Post-processing: duplicate detection, agency-per-section stats.

Building/section/off-plan classification already happens per-listing in
parse_detail.py; this module works across the whole collected set.
"""
from collections import Counter, defaultdict


class _UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _same_location(a, b):
    if a.get("building") and b.get("building"):
        return a["building"] == b["building"]
    if a.get("section") and b.get("section"):
        return a["section"] == b["section"]
    # neither has a resolved building/section: fall back to municipality,
    # which is coarse but keeps dedup from silently no-op-ing.
    return (a.get("municipality") or "") == (b.get("municipality") or "")


def _close_enough(a, b):
    size_a, size_b = a.get("size_sqm"), b.get("size_sqm")
    if size_a is None or size_b is None or abs(size_a - size_b) > 1.5:
        return False
    floor_a, floor_b = a.get("floor_numeric"), b.get("floor_numeric")
    if floor_a is not None and floor_b is not None and floor_a != floor_b:
        return False
    price_a, price_b = a.get("price_eur"), b.get("price_eur")
    if price_a and price_b:
        if abs(price_a - price_b) / max(price_a, price_b) > 0.06:
            return False
    return _same_location(a, b)


def detect_duplicates(listings):
    """Mutates listings in place, adding duplicate_group_id / is_duplicate / duplicate_count.

    Only compares listings of the same ad_type against each other. Two
    listings are considered the same physical unit when they share a
    building/section (or municipality as a last resort), have matching
    floor (if both known), size within 1.5 sqm, and price within 6%.
    """
    by_type = defaultdict(list)
    for i, l in enumerate(listings):
        by_type[l.get("ad_type")].append(i)

    for _, idxs in by_type.items():
        uf = _UnionFind(len(idxs))
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                i, j = idxs[a_pos], idxs[b_pos]
                if _close_enough(listings[i], listings[j]):
                    uf.union(a_pos, b_pos)

        groups = defaultdict(list)
        for pos in range(len(idxs)):
            groups[uf.find(pos)].append(idxs[pos])

        for root, members in groups.items():
            group_id = None
            if len(members) > 1:
                group_id = "dup-" + "-".join(sorted(str(listings[m].get("listing_id") or m) for m in members))
            for m in members:
                listings[m]["is_duplicate"] = len(members) > 1
                listings[m]["duplicate_count"] = len(members)
                listings[m]["duplicate_group_id"] = group_id
                listings[m]["duplicate_agencies"] = sorted({
                    (listings[x].get("agency_name") or ("Owner" if listings[x].get("is_owner") else "Unknown"))
                    for x in members
                }) if len(members) > 1 else []

    return listings


def agency_leaderboard_by_section(listings):
    """Which agency has the most active *sale* listings in each BW section/building."""
    counts = defaultdict(Counter)
    for l in listings:
        if l.get("ad_type") != "prodaja" or l.get("is_owner"):
            continue
        key = l.get("section") or l.get("building") or "Unspecified"
        agency = l.get("agency_name") or "Unknown"
        counts[key][agency] += 1

    result = {}
    for section, counter in counts.items():
        top = counter.most_common()
        result[section] = [{"agency": a, "count": c} for a, c in top]
    return result
