"""Feature experiments, 11-year leave-one-year-out at voting close. Writes reports/experiments.csv."""
import sys, json
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
from harness import loyo, metrics, summary, CORE_FEATURES
from history import HIST

def add_split(f):
    f = f.copy()
    k = ["countdown_year", "snapshot", "lead"]
    f["vs_rank_tj"] = f.groupby(k)["tj_cum"].rank(ascending=False, method="first")
    f["vs_rank_sp"] = f.groupby(k)["sp_cum"].rank(ascending=False, method="first")
    strong = (f["p_tj_cum"] > 0.9) | (f["p_sp_cum"] > 0.95)
    f["vs_n_strong"] = strong.groupby([f[c] for c in k]).transform("sum")
    return f

SPLIT = ["vs_rank_tj", "vs_rank_sp", "vs_n_strong", "p_tj_artist_share"]
SETS = {
    "core": CORE_FEATURES,
    "core+aus": CORE_FEATURES + ["is_aus"],
    "core+hist": CORE_FEATURES + HIST,
    "core+aus+hist": CORE_FEATURES + ["is_aus"] + HIST,
    "core+aus+hist+split": CORE_FEATURES + ["is_aus"] + HIST + SPLIT,
}

if __name__ == "__main__":
    which = sys.argv[1:] or list(SETS)
    f = add_split(pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet"))
    out = ROOT / "reports/experiments.csv"
    prev = pd.read_csv(out) if out.exists() else pd.DataFrame()
    rows = []
    for name in which:
        p = loyo(f, SETS[name])
        p.to_parquet(ROOT / f"data/derived/loyo_preds_{name}.parquet", index=False)
        m = metrics(p); s = summary(m); s["name"] = name
        s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank)
        rows.append(s); print(s, flush=True)
    res = pd.concat([prev[~prev.get("name", pd.Series(dtype=str)).isin(which)] if len(prev) else prev, pd.DataFrame(rows)])
    res.to_csv(out, index=False)
