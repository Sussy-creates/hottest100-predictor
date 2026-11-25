"""Robustness of the pairwise objective: other seeds, and on smaller feature sets."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import pandas as pd
from harness import loyo, metrics, summary, CORE_FEATURES
from history import HIST
from model_variants import grouped_fit, PARAMS
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
import numpy as np, xgboost as xgb
from h100.model import relevance
def pw(seeds):
    def fit(tr, te, ft):
        tr = tr.sort_values("countdown_year"); groups = tr.groupby("countdown_year").size().to_numpy(); zs = []
        for s in seeds:
            m = xgb.XGBRanker(**{**PARAMS, "objective": "rank:pairwise"}, random_state=s); m.fit(tr[ft], relevance(tr["rank"]), group=groups)
            p = m.predict(te[ft]); zs.append((p - p.mean()) / (p.std() + 1e-9))
        return np.mean(zs, axis=0)
    return fit
runs = [("core pairwise", CORE_FEATURES, (1, 2, 3, 4, 7)), ("core+aus pairwise", CORE_FEATURES + ["is_aus"], (1, 2, 3, 4, 7)),
        ("core+aus+hist pairwise seeds11-15", CORE_FEATURES + ["is_aus"] + HIST, (11, 12, 13, 14, 15))]
for name, ft, seeds in runs:
    p = loyo(f, ft, fitter=pw(seeds)); p.to_parquet(ROOT / f"data/derived/loyo_preds_{name.replace(' ', '_')}.parquet", index=False)
    m = metrics(p); s = summary(m); s["name"] = name
    s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank); print(s, flush=True)
