"""The frozen model: XGBoost ranker on snapshot features, averaged over seeds."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from .rule import POOL

CORE_FEATURES = POOL + ["sp_charted", "is_lav"]
PARAMS = dict(objective="rank:ndcg", n_estimators=200, max_depth=3, learning_rate=0.05,
              subsample=0.8, colsample_bytree=0.8)
SEEDS = (1, 2, 3, 4, 7)


def relevance(rank: pd.Series) -> np.ndarray:
    """Graded target: winner 5, top 5 4, top 10 3, top 50 2, top 200 1, else 0."""
    r = rank.to_numpy()
    return np.select([r == 1, r <= 5, r <= 10, r <= 50, r <= 200], [5, 4, 3, 2, 1], 0)


def fit(train: pd.DataFrame, features: list[str], seeds=SEEDS) -> list:
    tr = train.sort_values("countdown_year")
    groups = tr.groupby("countdown_year").size().to_numpy()
    models = []
    for s in seeds:
        m = xgb.XGBRanker(**PARAMS, random_state=s)
        m.fit(tr[features], relevance(tr["rank"]), group=groups)
        models.append(m)
    return models


def predict(models: list, frame: pd.DataFrame, features: list[str]) -> pd.Series:
    """Mean of per-seed scores after standardising each within the frame (scores are only comparable within a year)."""
    zs = []
    for m in models:
        s = m.predict(frame[features])
        zs.append((s - s.mean()) / (s.std() + 1e-9))
    return pd.Series(np.mean(zs, axis=0), index=frame.index)


def save_spec(path: Path, features: list[str], note: str) -> None:
    path.write_text(json.dumps({"model": "XGBRanker", "params": PARAMS, "seeds": list(SEEDS),
                                "features": features, "snapshot": 0, "train_years": "2015-2024",
                                "note": note}, indent=1))
