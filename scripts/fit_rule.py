"""Search weighted-percentile rules leave-one-year-out; compare with baselines and models.

Writes data/derived/rule_search.json and reports/model_comparison.csv.
Uses training years only (2015-2024) at snapshot T-0.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.rule import POOL, add_derived, evaluate, score  # noqa: E402

MAX_TERMS, WEIGHTS = 5, (1, 2, 3)


def combos():
    for k in range(1, MAX_TERMS + 1):
        for feats in itertools.combinations(range(len(POOL)), k):
            for ws in itertools.product(WEIGHTS, repeat=k):
                if k > 1 and np.gcd.reduce(ws) > 1:
                    continue  # (2,2) is the same rule as (1,1)
                w = np.zeros(len(POOL), dtype=np.float32)
                w[list(feats)] = ws
                yield w


def grid_metrics(f: pd.DataFrame, W: np.ndarray):
    """For every rule (column of W) and year: top-10 overlap and the winner's predicted rank."""
    years = sorted(f["countdown_year"].unique())
    ov = np.zeros((len(years), W.shape[1]), dtype=np.int16)
    wr = np.zeros((len(years), W.shape[1]), dtype=np.int32)
    for i, y in enumerate(years):
        g = f[f["countdown_year"] == y]
        X = g[POOL].to_numpy(np.float32)
        tie = (1e-4 * g["p_tj_peak7"].to_numpy(np.float32))[:, None]
        r = g["rank"].to_numpy()
        win = int(np.flatnonzero(r == 1)[0])
        for a in range(0, W.shape[1], 20000):
            S = X @ W[:, a:a + 20000] + tie
            top = np.argpartition(-S, 10, axis=0)[:10]
            ov[i, a:a + 20000] = (r[top] <= 10).sum(axis=0)
            wr[i, a:a + 20000] = 1 + (S > S[win]).sum(axis=0)
    return years, ov, wr


def objective(ov, wr):
    """Mean top-10 overlap share plus share of years with the winner in the predicted top 3."""
    return ov.mean(axis=0) / 10 + (wr <= 3).mean(axis=0)


def rule_dict(w):
    return {POOL[i]: float(w[i]) for i in np.flatnonzero(w)}


def main() -> None:
    f = add_derived(pd.read_parquet(ROOT / "data" / "derived" / "features.parquet"))
    f = f[f["snapshot"] == 0].reset_index(drop=True)
    W = np.stack(list(combos()), axis=1)
    print(f"{W.shape[1]:,} rules x {f['countdown_year'].nunique()} years", flush=True)
    years, ov, wr = grid_metrics(f, W)

    # Leave-one-year-out: choose on nine years, score the tenth.
    loyo, chosen = [], []
    for i, y in enumerate(years):
        keep = [j for j in range(len(years)) if j != i]
        best = int(np.argmax(objective(ov[keep], wr[keep])))
        chosen.append(rule_dict(W[:, best]))
        loyo.append({"countdown_year": y, "top10_overlap": int(ov[i, best]), "winner_pred_rank": int(wr[i, best]),
                     "rule": json.dumps(rule_dict(W[:, best]))})
    loyo = pd.DataFrame(loyo)

    J = objective(ov, wr)
    order = np.argsort(-J)[:15]
    final = rule_dict(W[:, order[0]])
    top = [{"rule": rule_dict(W[:, j]), "objective": float(J[j]), "mean_top10": float(ov[:, j].mean()),
            "winner_top3_years": int((wr[:, j] <= 3).sum()), "winner_hit_years": int((wr[:, j] == 1).sum())}
           for j in order]

    # Comparators, all scored the same way.
    res = {"rule (in-sample best)": evaluate(f, lambda y, g: score(g, final)),
           "baseline: most played triple j": evaluate(f, lambda y, g: score(g, {"p_tj_cum": 1})),
           "baseline: most streamed Spotify AU": evaluate(f, lambda y, g: score(g, {"p_sp_cum": 1})),
           "baseline: peak weekly airplay": evaluate(f, lambda y, g: score(g, {"p_tj_peak7": 1}))}
    res["rule (leave-one-year-out)"] = loyo.assign(winner_top3=(loyo["winner_pred_rank"] <= 3).astype(int),
                                                   winner_hit=(loyo["winner_pred_rank"] == 1).astype(int))

    feats = POOL + ["sp_charted", "is_lav"]
    from sklearn.linear_model import LogisticRegression
    import xgboost as xgb

    def loyo_model(make, fit):
        def scorer(y, g):
            tr = f[f["countdown_year"] != y]
            m = make()
            fit(m, tr)
            return pd.Series(m_predict(m, g), index=g.index)
        return scorer

    def m_predict(m, g):
        return m.predict_proba(g[feats])[:, 1] if hasattr(m, "predict_proba") else m.predict(g[feats])

    res["model: logistic regression"] = evaluate(f, loyo_model(
        lambda: LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000),
        lambda m, tr: m.fit(tr[feats], (tr["rank"] <= 10).astype(int))))

    def fit_rank(m, tr):
        tr = tr.sort_values("countdown_year")
        rel = np.select([tr["rank"] == 1, tr["rank"] <= 5, tr["rank"] <= 10, tr["rank"] <= 50, tr["rank"] <= 200],
                        [5, 4, 3, 2, 1], 0)
        m.fit(tr[feats], rel, group=tr.groupby("countdown_year").size().to_numpy())

    res["model: XGBoost ranker"] = evaluate(f, loyo_model(
        lambda: xgb.XGBRanker(objective="rank:ndcg", n_estimators=200, max_depth=3, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.8, random_state=7), fit_rank))

    summary = []
    for name, r in res.items():
        summary.append({"method": name, "mean_top10_overlap": round(r["top10_overlap"].mean(), 2),
                        "winner_hit_years": int((r["winner_pred_rank"] == 1).sum()),
                        "winner_top3_years": int((r["winner_pred_rank"] <= 3).sum()),
                        "median_winner_rank": float(r["winner_pred_rank"].median())})
    summary = pd.DataFrame(summary)
    (ROOT / "reports").mkdir(exist_ok=True)
    summary.to_csv(ROOT / "reports" / "model_comparison.csv", index=False)
    per_year = pd.concat({k: v.set_index("countdown_year") for k, v in res.items()}, names=["method"])
    per_year.to_csv(ROOT / "reports" / "model_comparison_by_year.csv")
    (ROOT / "data" / "derived" / "rule_search.json").write_text(json.dumps(
        {"final_rule": final, "top_rules": top, "loyo_chosen": chosen, "n_rules": int(W.shape[1])}, indent=1))
    pd.set_option("display.width", 200)
    print(summary.to_string(index=False))
    print("\nfinal rule:", final)
    print("\nLOYO picks:\n", loyo.to_string(index=False))


if __name__ == "__main__":
    main()
