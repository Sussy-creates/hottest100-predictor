"""Pairwise XGBRanker fitter for the LOYO harness (seed-averaged z-scores)."""
import numpy as np, xgboost as xgb
from h100.model import relevance, PARAMS

def pw(seeds=(1, 2, 3, 4, 7)):
    def fit(tr, te, ft):
        tr = tr.sort_values("countdown_year"); groups = tr.groupby("countdown_year").size().to_numpy(); zs = []
        for s in seeds:
            m = xgb.XGBRanker(**{**PARAMS, "objective": "rank:pairwise"}, random_state=s)
            m.fit(tr[ft], relevance(tr["rank"]), group=groups)
            p = m.predict(te[ft]); zs.append((p - p.mean()) / (p.std() + 1e-9))
        return np.mean(zs, axis=0)
    return fit
