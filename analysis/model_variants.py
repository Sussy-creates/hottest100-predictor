"""Model-side variants on core+aus+hist: more training snapshots, pairwise objective."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd, xgboost as xgb
from harness import loyo, metrics, summary, CORE_FEATURES
from history import HIST
from h100.model import relevance, PARAMS
feats = CORE_FEATURES + ["is_aus"] + HIST
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")

def grouped_fit(tr, te, feats, params):
    tr = tr.sort_values(["countdown_year", "snapshot"])
    groups = tr.groupby(["countdown_year", "snapshot"], sort=False).size().to_numpy()
    zs = []
    for s in (1, 2, 3, 4, 7):
        m = xgb.XGBRanker(**params, random_state=s); m.fit(tr[feats], relevance(tr["rank"]), group=groups)
        p = m.predict(te[feats]); zs.append((p - p.mean()) / (p.std() + 1e-9))
    return np.mean(zs, axis=0)

variants = {
    "train T0+T30": dict(train_snapshot=[0, 30], fitter=lambda tr, te, ft: grouped_fit(tr, te, ft, PARAMS)),
    "pairwise": dict(fitter=lambda tr, te, ft: grouped_fit(tr, te, ft, {**PARAMS, "objective": "rank:pairwise"})),
}
for name, kw in variants.items():
    m = metrics(loyo(f, feats, **kw)); s = summary(m); s["name"] = "core+aus+hist " + name
    s["per_year_top10"] = " ".join(map(str, m.top10)); print(s, flush=True)
