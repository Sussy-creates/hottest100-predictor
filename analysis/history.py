"""Artist history features: how the song's lead artist did in previous countdowns (all known before voting)."""
import re, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from h100.normalize import ascii_lower

SPLIT = re.compile(r"\s+(?:featuring|feat\.?|ft\.?|with|x|vs\.?|&|and)\s+|,\s*|\s+/\s+", re.I)

def lead(artist: str) -> str:
    a = SPLIT.split(ascii_lower(str(artist)))[0].strip()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", a))

def add_history(f: pd.DataFrame) -> pd.DataFrame:
    h = pd.read_csv(ROOT / "data/derived/results_history.csv")
    h["lead"] = h["artist"].map(lead)
    f = f.copy(); f["lead"] = f["artist"].map(lead)
    feats = []
    for y in sorted(f.countdown_year.unique()):
        past = h[h.countdown_year < y]
        def agg(lo, top=100):
            p = past[(past.countdown_year >= y - lo) & (past["rank"] <= top)]
            return p.groupby("lead")
        g1, g3, g5, g10 = agg(1, 200), agg(3, 200), agg(5), agg(10)
        d = pd.DataFrame({"lead": f.loc[f.countdown_year == y, "lead"].unique()})
        d["countdown_year"] = y
        d["ah_prev1_best"] = d.lead.map(g1["rank"].min()).fillna(201)
        d["ah_prev1_n"] = d.lead.map(g1.size()).fillna(0)
        d["ah_best3"] = d.lead.map(g3["rank"].min()).fillna(201)
        d["ah_n3"] = d.lead.map(g3.size()).fillna(0)
        d["ah_top10_5y"] = d.lead.map(past[(past.countdown_year >= y - 5) & (past["rank"] <= 10)].groupby("lead").size()).fillna(0)
        d["ah_years10"] = d.lead.map(g10["countdown_year"].nunique()).fillna(0)
        feats.append(d)
    return f.merge(pd.concat(feats), on=["countdown_year", "lead"], how="left")

HIST = ["ah_prev1_best", "ah_prev1_n", "ah_best3", "ah_n3", "ah_top10_5y", "ah_years10"]

if __name__ == "__main__":
    f = add_history(pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet"))
    f.to_parquet(ROOT / "data/derived/analysis_frame.parquet", index=False)
    g = f[f.snapshot == 0]
    g["band"] = pd.cut(g["rank"], [0, 10, 50, 200, 999], labels=["1-10", "11-50", "51-200", "unranked"])
    print(g.groupby("band", observed=True)[["ah_n3", "ah_years10"]].agg(lambda s: (s > 0).mean()).round(2))
    print(g[(g["rank"] <= 10)].groupby("is_aus")[["ah_n3"]].agg(lambda s: (s > 0).mean()))
