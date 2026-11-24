"""Add-on signals from archived chart captures (YouTube AU, Shazam AU).

Coverage is patchy, so for each year we report how many captures fall in the window, and leave
features missing (NaN) where there are none, rather than pretending a song was absent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .matching import find, index
from .normalize import artist_tokens, title_keys, version_of

WINDOW = 60  # days before close


def chart_features(f: pd.DataFrame, chart: pd.DataFrame, cal: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """f: feature rows (countdown_year, snapshot, song_id, title, artist). chart: rank, artist, title, captured."""
    out = []
    cand = f.drop_duplicates(["countdown_year", "song_id"])[["countdown_year", "song_id", "title", "artist"]].copy()
    k = cand["title"].map(title_keys)
    cand["k_short"], cand["k_full"] = k.str[0], k.str[1]
    cand["version"] = cand["title"].map(version_of)
    cand["atok"] = cand["artist"].map(lambda a: artist_tokens(*str(a).split(", ")))
    cand = cand.rename(columns={"song_id": "ident"})

    chart = chart.copy()
    chart["captured"] = pd.to_datetime(chart["captured"]).dt.tz_localize(None)
    for (y, d), g in f.groupby(["countdown_year", "snapshot"]):
        close = pd.Timestamp(str(cal.loc[cal["countdown_year"] == y, "voting_close_aedt"].iloc[0])[:10])
        T = close - pd.Timedelta(days=d)
        w = chart[(chart["captured"] < T) & (chart["captured"] >= T - pd.Timedelta(days=WINDOW))]
        n_caps = w["captured"].dt.normalize().nunique()
        res = pd.DataFrame({"countdown_year": y, "snapshot": d, "song_id": g["song_id"].values})
        res[f"{prefix}_captures"] = n_caps
        if n_caps == 0:
            res[f"{prefix}_best_rank"] = np.nan
            res[f"{prefix}_present"] = np.nan
            out.append(res)
            continue
        cy = cand[cand["countdown_year"] == y]
        idx = index(cy, ["k_short", "k_full"])
        pool = {r.ident: r for r in cy.itertuples()}
        by_art: dict = {}
        for r in pool.values():
            for a in r.atok:
                by_art.setdefault(a, []).append(r)
        best: dict = {}
        for r in w.groupby(["artist", "title"])["rank"].min().reset_index().itertuples():
            hit, _ = find(set(title_keys(r.title)), version_of(r.title), artist_tokens(*str(r.artist).split(", ")),
                          idx, pool, by_art, allow_title_only=False)
            for h in hit:
                best[h.ident] = min(best.get(h.ident, 999), r.rank)
        res[f"{prefix}_best_rank"] = res["song_id"].map(best).fillna(250)
        res[f"{prefix}_present"] = res["song_id"].isin(best).astype(float)
        out.append(res)
    o = pd.concat(out, ignore_index=True)
    # Percentile within year/snapshot, lower rank is better; NaN where the year has no captures.
    o[f"p_{prefix}_best_rank"] = o.groupby(["countdown_year", "snapshot"])[f"{prefix}_best_rank"].rank(
        pct=True, ascending=False)
    return o
