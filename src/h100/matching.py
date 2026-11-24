"""Candidate lookup shared by countdown matching and feature building."""
from __future__ import annotations

from collections import defaultdict

from .normalize import artists_overlap, titles_close


def index(df, key_cols):
    idx = defaultdict(list)
    for r in df.itertuples():
        for k in {getattr(r, c) for c in key_cols}:
            idx[(k, r.version)].append(r)
    return idx


def find(entry_keys, ver, at, idx, pool, by_artist, allow_title_only=True):
    """Exact key + artist; else unique exact key; else fuzzy key + artist. Returns (hits, method)."""
    exact = [x for k in entry_keys for x in idx.get((k, ver), []) if x.ident in pool]
    hit = [x for x in exact if artists_overlap(x.atok, at)]
    if hit:
        return hit, "title+artist"
    if allow_title_only and len({x.ident for x in exact}) == 1:
        return exact, "title_only"
    near = {x.ident: x for a in at for x in by_artist.get(a, [])}
    fuzzy = [x for x in near.values() if x.version == ver
             and any(titles_close(k, x.k_short) or titles_close(k, x.k_full) for k in entry_keys)]
    return (fuzzy, "fuzzy") if fuzzy else ([], "unmatched")


def pool(df, lo_col, hi_col, start, end):
    sub = df[(df[hi_col] >= start) & (df[lo_col] <= end)]
    pool = {r.ident: r for r in sub.itertuples()}
    by_artist = defaultdict(list)
    for r in pool.values():
        for a in r.atok:
            by_artist[a].append(r)
    return pool, by_artist
