"""Model v2: core features + cleaned Australian flag, pairwise XGBRanker, previous-countdown filter,
plus calibrated probabilities (win, top 5, top 10) for betting.

  python analysis/v2.py loyo   # 11-year leave-one-year-out scores, temperature fit, calibration report
  python analysis/v2.py live   # train on 2015-2025, score the latest data/live/features_*.parquet

Probabilities: each song's chance comes from a Plackett-Luce model on the score, P(first) = softmax(score / tau).
Separate temperatures are fitted on the LOYO scores for the winner and for top-5/top-10 membership (Gumbel
simulation), each mixed with a small even spread (eps) over the whole field for freak results.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd  # noqa: E402
from aus_fix import aus_fixed  # noqa: E402
from harness import CORE_FEATURES, loyo, metrics, summary  # noqa: E402
from pairwise_fit import pw  # noqa: E402
from prev_filter import prev_rank  # noqa: E402

FEATURES = CORE_FEATURES + ["is_aus2"]
SEEDS = (1, 2, 3, 4, 7, 11, 12, 13, 14, 15)
SIMS = 20000
CAL = ROOT / "config/model_v2_calibration.json"


def prepare(f: pd.DataFrame) -> pd.DataFrame:
    f = f[f.snapshot == 0].copy()
    f["is_aus2"] = aus_fixed(f)
    f["prev_rank"] = prev_rank(f)
    return f[f.prev_rank.isna()].copy()


def place_probs(score: np.ndarray, tau: float, k: int, rng, sims: int = SIMS, field: int = 400) -> np.ndarray:
    """P(song finishes in the top k) under Plackett-Luce, by Gumbel-max simulation over the top `field` songs
    (songs further down have effectively no chance and are given zero)."""
    idx = np.argsort(-score)[:field]
    s = score[idx] / tau
    hits = np.zeros(len(s))
    for _ in range(max(sims // 1000, 1)):
        g = s[None, :] + rng.gumbel(size=(1000, len(s)))
        top = np.argpartition(-g, k - 1, axis=1)[:, :k]
        np.add.at(hits, top.ravel(), 1)
    out = np.zeros(len(score))
    out[idx] = hits / (max(sims // 1000, 1) * 1000)
    return out


def win_probs(score: np.ndarray, tau: float) -> np.ndarray:
    s = score / tau
    e = np.exp(s - s.max())
    return e / e.sum()


EPS = (0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4)


def fit_taus(p: pd.DataFrame) -> dict:
    """Fit (tau, eps) per target by log-likelihood on the LOYO scores. eps is the share of probability spread
    evenly over the whole field: it absorbs freak outcomes (the 2021 Wiggles cover was ranked 748th), which
    would otherwise force a flat tau that understates the favourite."""
    taus = np.round(np.exp(np.linspace(np.log(0.05), np.log(2), 24)), 4)
    years = [g for _, g in p.groupby("countdown_year")]
    best = {}
    ll = {(t, e): sum(np.log((1 - e) * win_probs(g.score.values, t)[(g["rank"] == 1).values].sum() + e / len(g))
                      for g in years) for t in taus for e in EPS}
    (t, e), v = max(ll.items(), key=lambda kv: kv[1])
    best.update(tau_win=float(t), eps_win=float(e), winner_loglik=float(v))
    rng = np.random.default_rng(0)
    for k in (5, 10):
        ll = {}
        for t in taus[::2]:
            qs = [place_probs(g.score.values, t, k, rng, sims=3000) for g in years]
            for e in EPS:
                tot = 0.0
                for g, q in zip(years, qs):
                    q2 = np.clip((1 - e) * q + e * k / len(g), 1e-5, 1 - 1e-5)
                    y = (g["rank"] <= k).values
                    tot += np.sum(y * np.log(q2) + (1 - y) * np.log(1 - q2))
                ll[(t, e)] = tot
        (t, e), v = max(ll.items(), key=lambda kv: kv[1])
        best[f"tau_top{k}"], best[f"eps_top{k}"] = float(t), float(e)
    # Top-5 / top-10 chances used for betting: logistic on log(predicted rank). Better calibrated than the
    # Plackett-Luce version and checked year-out (reports/v2_calibration.txt); PL values are kept for reference.
    from sklearn.linear_model import LogisticRegression
    X = np.log(p[["pred_rank"]].values)
    for k in (5, 10):
        m = LogisticRegression(C=100).fit(X, (p["rank"] <= k).values)
        best[f"rank_logit_top{k}"] = [float(m.intercept_[0]), float(m.coef_[0][0])]
    return best


def add_probs(g: pd.DataFrame, cal: dict, rng) -> pd.DataFrame:
    g = g.copy()
    n = len(g)
    g["p_win"] = (1 - cal["eps_win"]) * win_probs(g.score.values, cal["tau_win"]) + cal["eps_win"] / n
    g["p_top5"] = (1 - cal["eps_top5"]) * place_probs(g.score.values, cal["tau_top5"], 5, rng) + cal["eps_top5"] * 5 / n
    g["p_top10"] = (1 - cal["eps_top10"]) * place_probs(g.score.values, cal["tau_top10"], 10, rng) + cal["eps_top10"] * 10 / n
    r = g.score.rank(ascending=False, method="first").values
    for k in (5, 10):
        a, b = cal[f"rank_logit_top{k}"]
        g[f"p_top{k}_pl"] = g[f"p_top{k}"]
        g[f"p_top{k}"] = 1 / (1 + np.exp(-(a + b * np.log(r))))
    g["fair_odds_win"] = (1 / g.p_win).round(1)
    g["fair_odds_top10"] = (1 / g.p_top10).round(2)
    return g


def calibration_report(p: pd.DataFrame) -> str:
    lines = []
    for col, k, bins in (("p_top10", 10, [0, .05, .15, .3, .5, .7, 1.01]), ("p_win", 1, [0, .02, .05, .1, .2, .4, 1.01])):
        b = pd.cut(p[col], bins, right=False)
        t = p.groupby(b, observed=True).agg(n=(col, "size"), predicted=(col, "mean"), actual=("rank", lambda r: (r <= k).mean()))
        lines.append(f"\n{col} calibration (11 LOYO years)\n" + t.round(3).to_string())
    fav = p.sort_values("p_win", ascending=False).groupby("countdown_year").head(1)
    lines.append(f"\nModel favourite: mean p_win {fav.p_win.mean():.2f}, won {int((fav['rank'] == 1).sum())} of {len(fav)}")
    return "\n".join(lines)


def main(mode: str) -> None:
    f = prepare(pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet"))
    if mode == "loyo":
        cache = ROOT / "data/derived/loyo_scores_v2.parquet"
        if cache.exists() and "--refit" not in sys.argv:
            p = pd.read_parquet(cache)
        else:
            p = loyo(f, FEATURES, fitter=pw(SEEDS)); p.to_parquet(cache, index=False)
        m = metrics(p); s = summary(m)
        print(s, "\nper-year top10:", " ".join(map(str, m.top10)), "\nper-year winner rank:", " ".join(str(int(x)) for x in m.winner_rank), flush=True)
        cal = fit_taus(p); cal["seeds"] = list(SEEDS); cal["features"] = FEATURES; cal["loyo"] = s
        CAL.write_text(json.dumps(cal, indent=1))
        rng = np.random.default_rng(1)
        p = pd.concat([add_probs(g, cal, rng) for _, g in p.groupby("countdown_year")])
        p.to_parquet(ROOT / "data/derived/loyo_preds_v2.parquet", index=False)
        rep = json.dumps({k: v for k, v in cal.items() if k.startswith(("tau", "eps")) or k == "winner_loglik"}) + calibration_report(p)
        (ROOT / "reports/v2_calibration.txt").write_text(rep)
        print(rep)
    else:
        from h100.rule import add_derived
        cal = json.loads(CAL.read_text())
        path = sorted((ROOT / "data/live").glob("features_*.parquet"))[-1]
        live = add_derived(pd.read_parquet(path))
        plays = pd.read_parquet(ROOT / "data/derived/plays.parquet", columns=["recording_id", "song_id"])
        top = plays.groupby(["song_id", "recording_id"]).size().reset_index(name="n").sort_values("n").drop_duplicates("song_id", keep="last")
        meta = pd.read_parquet(ROOT / "data/derived/recording_meta.parquet")
        live["is_aus"] = live.song_id.map(top.merge(meta, on="recording_id").set_index("song_id")["aus_any"]).fillna(False).astype(float)
        live = prepare(live)
        live["score"] = pw(SEEDS)(f, live, FEATURES)
        out = add_probs(live, cal, np.random.default_rng(1)).sort_values("score", ascending=False)
        out["pred_rank"] = range(1, len(out) + 1)
        stamp = path.stem.replace("features_", "")
        cols = ["pred_rank", "title", "artist", "p_win", "fair_odds_win", "p_top5", "p_top10", "fair_odds_top10",
                "is_aus2", "tj_cum", "sp_cum", "sp_best_rank"]
        out.head(100)[cols].to_csv(ROOT / f"reports/live_{stamp}_v2.csv", index=False)
        print(out.head(25)[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loyo")
