"""Text/number normalization helpers shared by the parsers."""
import re
import unicodedata

_DIACRITIC_MAP = str.maketrans({
    "č": "c", "ć": "c", "ž": "z", "š": "s", "đ": "dj",
    "Č": "c", "Ć": "c", "Ž": "z", "Š": "s", "Đ": "dj",
})


def fold(text):
    """Lowercase + strip Serbian diacritics, for robust label matching."""
    if not text:
        return ""
    return text.translate(_DIACRITIC_MAP).lower().strip()


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_number(text):
    """Parse a Serbian-formatted number ('.'=thousands, ','=decimal) to float.

    Only the first contiguous digit run (with internal '.'/',' separators) is
    used, so unit suffixes glued onto the number by a stray digit (e.g. "65
    m2" must NOT become "652") are excluded: a run stops at the first
    non-digit/separator character such as a space.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(r"-?\d[\d.,]*", str(text))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # ambiguous: "56,5" (decimal) vs "56,500" (thousands) — real-estate
        # sqm/price-per-sqm rarely has 3 decimal digits, so treat 3-digit
        # groups after a comma as thousands, else as decimal.
        head, _, tail = s.rpartition(",")
        s = (head + tail) if len(tail) == 3 else (head + "." + tail)
    else:
        # '.' as thousands separator, e.g. "123.456"
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            s = "".join(parts)
    try:
        return float(s)
    except ValueError:
        return None


def parse_int(text):
    n = parse_number(text)
    return int(n) if n is not None else None


FLOOR_WORDS = {
    "suteren": -1,
    "podrum": -1,
    "prizemlje": 0,
    "visoko prizemlje": 0,
    "vpr": 0,
    "potkrovlje": 99,  # sentinel, resolved relative to total_floors by caller if needed
}

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(text):
    """halooglasi reports the floor field in Roman numerals (e.g. "VII/15")."""
    s = (text or "").strip().upper()
    if not s or any(ch not in _ROMAN_VALUES for ch in s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


def _parse_floor_token(token):
    token = token.strip()
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    return _roman_to_int(token)


def parse_floor(text):
    """Returns (floor_numeric, total_floors) best-effort from a raw floor string."""
    if not text:
        return None, None
    t = clean_text(text)
    tf = fold(t)
    m = re.search(r"([IVXLCDM]+|-?\d+)\s*/\s*([IVXLCDM]+|\d+)", t, re.IGNORECASE)
    if m:
        cur = _parse_floor_token(m.group(1))
        tot = _parse_floor_token(m.group(2))
        if cur is not None:
            return cur, tot
    for word, val in FLOOR_WORDS.items():
        if word in tf:
            return val, None
    m = re.search(r"-?\d+", t)
    if m:
        return int(m.group(0)), None
    roman = _roman_to_int(t)
    if roman is not None:
        return roman, None
    return None, None
