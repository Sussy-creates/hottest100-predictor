"""Scoring rule: a weighted sum of within-year feature percentiles, plus the metrics used to judge it."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

POOL = ["p_sp_cum", "p_sp_best_rank", "p_sp_weeks", "p_sp_last4",
        "p_tj_peak7", "p_tj_cum", "p_tj_last28", "p_tj_since_liftoff", "p_tj_fade",
        "p_tj_artist_plays", "artist_many", "lav_rel"]


def add_derived(f: pd.DataFrame) -> pd.DataFrame:
    """Features defined relative to other candidates in the same year and snapshot."""
    f = f.copy()
    f["artist_many"] = 1 - f["p_tj_artist_songs"]  # artists with more eligible songs score higher
    lav = f["is_lav"] == 1
    f["lav_rel"] = 0.0
    f.loc[lav, "lav_rel"] = f[lav].groupby(["countdown_year", "snapshot"])["tj_cum"].rank(pct=True)
    return f


def score(f: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=f.index)
    for k, w in weights.items():
        s += w * f[k]
    # Ties broken by peak weekly airplay, then cumulative plays (deterministic).
    return s + 1e-6 * f["p_tj_peak7"] + 1e-9 * f["p_tj_cum"]


def year_metrics(g: pd.DataFrame, s: pd.Series) -> dict:
    g = g.assign(score=s.loc[g.index]).sort_values("score", ascending=False)
    g["pred_rank"] = np.arange(1, len(g) + 1)
    top10 = g.head(10)
    win = g.loc[g["rank"] == 1, "pred_rank"]
    both = top10[top10["rank"] <= 10]
    rho = spearmanr(both["pred_rank"], both["rank"]).statistic if len(both) >= 3 else np.nan
    return {
        "top10_overlap": int((top10["rank"] <= 10).sum()),
        "top5_overlap": int((g.head(5)["rank"] <= 5).sum()),
        "winner_pred_rank": int(win.iloc[0]) if len(win) else 9999,
        "winner_hit": int(len(win) > 0 and win.iloc[0] == 1),
        "winner_top3": int(len(win) > 0 and win.iloc[0] <= 3),
        "top10_spearman": rho,
        "pred_1": f"{top10.iloc[0]['title']} - {top10.iloc[0]['artist']}",
    }


def evaluate(f: pd.DataFrame, scorer) -> pd.DataFrame:
    """scorer(year, frame) -> Series of scores aligned to frame.index."""
    rows = []
    for y, g in f.groupby("countdown_year"):
        rows.append({"countdown_year": y, **year_metrics(g, scorer(y, g))})
    return pd.DataFrame(rows)
