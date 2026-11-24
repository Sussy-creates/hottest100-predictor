"""Title and artist normalisation shared by triple j, Spotify and countdown matching."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

LAV = re.compile(r"like\s*a\s*version", re.I)
LIVE = re.compile(r"\blive\b|live recording|live at|live from", re.I)
KEEP = re.compile(r"remix|rework|\bvip\b|\bflip\b", re.I)  # versions that count as different songs
DROP = re.compile(r"radio edit|single version|album version|explicit|clean|remaster|original mix|extended|\bedit\b", re.I)
FEAT = re.compile(r"^\s*(feat\.?|ft\.?|featuring|with|prod\.?)\b", re.I)
FEAT_TAIL = re.compile(r"\s+\b(feat\.?|ft\.?|featuring)\s.*$", re.I)
BRACKET = re.compile(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]")
ART_SPLIT = re.compile(r"\s*(?:,|&|\+|\band\b|\bx\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bwith\b|\bvs\.?\b|/|\|)\s*", re.I)
SUBS = str.maketrans({"$": "s", "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss", "!": "i"})


def ascii_lower(s) -> str:
    s = str(s or "").translate(SUBS)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def version_of(*texts) -> str:
    """'lav', 'live' or '' from any descriptive strings (title, summary title, release title)."""
    joined = " ".join(t for t in texts if isinstance(t, str) and t)
    if LAV.search(joined):
        return "lav"
    if LIVE.search(joined) and re.search(r"[\(\[\{-]", joined):
        return "live"
    return ""


def _clean(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.replace("&", "and"))


def title_keys(title) -> tuple[str, str]:
    """(short, full) identity keys.

    short: brackets and ' - suffix' dropped unless they name a remix.
    full:  also keeps descriptive bracket text such as '(Season One)' or '(Tipsy)'.
    Featured artists, edits and version tags are dropped from both.
    """
    t = ascii_lower(title)
    short_keep, full_keep = [], []
    for part in BRACKET.findall(t):
        if FEAT.search(part) or LAV.search(part) or LIVE.search(part):
            continue
        if KEEP.search(part):
            short_keep.append(part)
            full_keep.append(part)
        elif not DROP.search(part):
            full_keep.append(part)
    t = BRACKET.sub(" ", t)
    if " - " in t:
        head, tail = t.split(" - ", 1)
        if KEEP.search(tail) and not LAV.search(tail):
            short_keep.append(tail)
            full_keep.append(tail)
        elif not (DROP.search(tail) or LAV.search(tail) or LIVE.search(tail) or FEAT.search(tail)):
            full_keep.append(tail)
        t = head
    t = FEAT_TAIL.sub("", t)
    short = _clean(t + " ".join(short_keep)) or _clean(ascii_lower(title))
    full = _clean(t + " ".join(full_keep)) or short
    return short, full


def title_key(title) -> str:
    return title_keys(title)[0]


def artist_tokens(*names) -> frozenset[str]:
    out = set()
    for n in names:
        for part in ART_SPLIT.split(ascii_lower(n)):
            part = re.sub(r"^the\s+", "", part.strip())
            part = re.sub(r"[^a-z0-9]", "", part)
            if part:
                out.add(part)
    return frozenset(out)


def artists_overlap(a: frozenset, b: frozenset) -> bool:
    if a & b:
        return True
    return any(len(x) >= 4 and len(y) >= 4 and (x.startswith(y) or y.startswith(x)) for x in a for y in b)


def titles_close(a: str, b: str) -> bool:
    """Near-identical titles. A remix never matches an original, nor part 2 its part 1."""
    if not a or not b or ("remix" in a) != ("remix" in b):
        return False
    if len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a)):
        rest = a[len(b):] if a.startswith(b) else b[len(a):]
        return not re.search(r"\d|pt|part", rest)
    return SequenceMatcher(None, a, b).ratio() >= 0.8
