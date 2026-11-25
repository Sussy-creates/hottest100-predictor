"""Google Trends features per candidate song (lead artist), at each snapshot.

From data/raw/trends/<year>.csv (daily, 4 artists + anchor per request):
  tr_level   artist interest / anchor interest over the 60 days before T (sums within the request)
  tr_recent  same over the 14 days before T
  tr_growth  tr_recent / mean level of days T-60..T-14
p_* versions are within-year, within-snapshot percentiles. Artists not fetched stay NaN.
Writes data/derived/trends_features.parquet.
"""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPLIT = re.compile(r"\s+(?:featuring|feat\.?|ft\.?|with|x|vs\.?|&|and)\s+|,\s*|\s+/\s+", re.I)
SNAPS = (0, 30, 60, 90, 120)


def lead_name(a):
    return SPLIT.split(str(a))[0].strip()


def artist_feats(tr: pd.DataFrame, T: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for a, g in tr.groupby("artist"):
        def ratio(lo, hi):
            w = g[(g.date >= lo) & (g.date < hi)]
            if w.empty:
                return np.nan
            return w.value.sum() / max(w.anchor.sum(), 1)
        lvl, rec, early = ratio(T - pd.Timedelta(days=60), T), ratio(T - pd.Timedelta(days=14), T), ratio(T - pd.Timedelta(days=60), T - pd.Timedelta(days=14))
        rows.append((a, lvl, rec, (rec + 0.01) / (early + 0.01) if pd.notna(early) else np.nan))
    return pd.DataFrame(rows, columns=["lead_name", "tr_level", "tr_recent", "tr_growth"])


def build(frame: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    out = []
    for y, fy in frame.groupby("countdown_year"):
        path = ROOT / "data/raw/trends" / f"{y}.csv"
        if not path.exists():
            continue
        tr = pd.read_csv(path).dropna(subset=["value"])
        tr["date"] = pd.to_datetime(tr["date"])
        close = cal.loc[y, "voting_close_aedt"]
        close = pd.Timestamp(str(close)[:10]) if isinstance(close, str) else tr.date.max() + pd.Timedelta(days=1)
        for d in sorted(fy.snapshot.unique()):
            g = fy[fy.snapshot == d][["countdown_year", "snapshot", "song_id", "artist"]].copy()
            g["lead_name"] = g.artist.map(lead_name)
            g = g.merge(artist_feats(tr, close - pd.Timedelta(days=int(d))), on="lead_name", how="left")
            for c in ["tr_level", "tr_recent", "tr_growth"]:
                g["p_" + c] = g[c].rank(pct=True)
            g["tr_have"] = g.tr_level.notna().astype(int)
            out.append(g.drop(columns=["artist"]))
    return pd.concat(out, ignore_index=True)


if __name__ == "__main__":
    cal = pd.read_csv(ROOT / "config/countdowns.csv").set_index("countdown_year")
    f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
    t = build(f, cal)
    t.to_parquet(ROOT / "data/derived/trends_features.parquet", index=False)
    print(t.groupby("countdown_year").tr_have.mean().round(2).to_string())
