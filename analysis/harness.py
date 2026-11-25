"""Leave-one-year-out harness over 2015-2025 with per-song predictions and stable metrics."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.model import CORE_FEATURES, fit, predict  # noqa: E402

def loyo(f: pd.DataFrame, feats, snapshot=0, train_snapshot=0, seeds=(1, 2, 3, 4, 7), fitter=None, years=None):
    """Per-song scores for every year, each from a model trained on the other years."""
    out = []
    ys = sorted(f.countdown_year.unique()) if years is None else years
    for y in ys:
        ts = train_snapshot if isinstance(train_snapshot, (list, tuple)) else [train_snapshot]
        tr = f[f.snapshot.isin(ts) & (f.countdown_year != y)]
        te = f[(f.snapshot == snapshot) & (f.countdown_year == y)].copy()
        if fitter is None:
            te["score"] = predict(fit(tr, feats, seeds), te, feats)
        else:
            te["score"] = fitter(tr, te, feats)
        te["pred_rank"] = te["score"].rank(ascending=False, method="first")
        out.append(te)
    return pd.concat(out, ignore_index=True)

def metrics(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y, g in p.groupby("countdown_year"):
        g = g.sort_values("pred_rank")
        act10 = set(g[g["rank"] <= 10].song_id); act5 = set(g[g["rank"] <= 5].song_id)
        act50 = set(g[g["rank"] <= 50].song_id)
        w = g[g["rank"] == 1]
        t10 = g[g["rank"] <= 10]
        rows.append(dict(countdown_year=y,
            top10=len(set(g.head(10).song_id) & act10), top5=len(set(g.head(5).song_id) & act5),
            top50=len(set(g.head(50).song_id) & act50),
            winner_rank=float(w.pred_rank.min()) if len(w) else np.nan,
            # continuous: mean log2 predicted rank of the actual top 10 (lower is better)
            top10_logrank=float(np.log2(t10.pred_rank).mean()),
            pred1=f"{g.iloc[0].title} - {g.iloc[0].artist}"))
    return pd.DataFrame(rows)

def summary(m: pd.DataFrame) -> dict:
    return dict(top10=round(m.top10.mean(), 2), top5=round(m.top5.mean(), 2), top50=round(m.top50.mean(), 1),
                winners=int((m.winner_rank == 1).sum()), winner_top3=int((m.winner_rank <= 3).sum()),
                med_winner=float(m.winner_rank.median()), logrank=round(m.top10_logrank.mean(), 3))
