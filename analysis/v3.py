"""Model v3 = model v2 score + Reddit ballot counts.

score_v3 = score_v2 + W * z(log1p(rd_votes)) within each year, where rd_votes is how many distinct Reddit users
listed the song in a ballot comment before voting closed (analysis/reddit_votes.py). W = 1 was the year-out choice
in every year (reports/reddit_blend.txt). Below 50 ballots the Reddit term is off, so before voting opens (and
in 2015, 8 ballots) v3 equals v2.

  python analysis/v3.py loyo   # blend the cached v2 LOYO scores, refit probability calibration
  python analysis/v3.py live   # score 2026: v2 live score + 2026 Reddit ballots so far
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd  # noqa: E402
import v2  # noqa: E402
from harness import metrics, summary  # noqa: E402
from reddit_votes import year_votes  # noqa: E402

W = 1.0
MIN_BALLOTS = 50  # below this the ballot counts are too sparse to z-score (2015 had 8: blending cost 4 top-10 hits)
CAL = ROOT / "config/model_v3_calibration.json"


def blend(p: pd.DataFrame, votes: pd.DataFrame) -> pd.DataFrame:
    p = p.drop(columns=[c for c in ("rd_votes", "rd_ballots") if c in p]).merge(
        votes[["countdown_year", "song_id", "rd_votes", "rd_ballots"]], on=["countdown_year", "song_id"], how="left")
    p["rd_votes"] = p.rd_votes.fillna(0)
    p["rd_ballots"] = p.groupby("countdown_year").rd_ballots.transform("max").fillna(0)
    out = []
    for _, g in p.groupby("countdown_year"):
        x = np.log1p(g.rd_votes)
        w = W if g.rd_ballots.iloc[0] >= MIN_BALLOTS else 0.0
        g = g.assign(score_v2=g.score, score=g.score + w * (x - x.mean()) / (x.std() + 1e-9) if x.std() > 0 else g.score)
        g["pred_rank"] = g.score.rank(ascending=False, method="first")
        out.append(g)
    return pd.concat(out)


def main(mode: str) -> None:
    cal_dates = pd.read_csv(ROOT / "config/countdowns.csv").set_index("countdown_year")
    if mode == "loyo":
        p = blend(pd.read_parquet(ROOT / "data/derived/loyo_scores_v2.parquet"),
                  pd.read_parquet(ROOT / "data/derived/reddit_votes.parquet"))
        m = metrics(p)
        print(summary(m), "\nper-year top10:", " ".join(map(str, m.top10)),
              "\nper-year winner rank:", " ".join(str(int(x)) for x in m.winner_rank), flush=True)
        cal = v2.fit_taus(p); cal["W"] = W; cal["loyo"] = summary(m)
        CAL.write_text(json.dumps(cal, indent=1))
        rng = np.random.default_rng(1)
        p = pd.concat([v2.add_probs(g, cal, rng) for _, g in p.groupby("countdown_year")])
        p.to_parquet(ROOT / "data/derived/loyo_preds_v3.parquet", index=False)
        rep = json.dumps({k: v for k, v in cal.items() if k.startswith(("tau", "eps")) or k == "winner_loglik"}) + v2.calibration_report(p)
        (ROOT / "reports/v3_calibration.txt").write_text(rep)
        print(rep)
    else:
        cal = json.loads(CAL.read_text())
        f = v2.prepare(pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet"))
        live, stamp = v2.live_scores(f)
        y = int(live.countdown_year.iloc[0])
        votes = year_votes(y, live[["song_id", "title", "artist"]], cal_dates)
        if votes is None:
            votes = live[["countdown_year", "song_id"]].assign(rd_votes=0, rd_ballots=0)
        live = blend(live, votes)
        if live.rd_ballots.max() < MIN_BALLOTS:  # Reddit term off: the scores are v2's, so use v2's calibration
            cal = json.loads(v2.CAL.read_text())
        out = v2.add_probs(live, cal, np.random.default_rng(1)).sort_values("score", ascending=False)
        out["pred_rank"] = range(1, len(out) + 1)
        out["v2_rank"] = out.score_v2.rank(ascending=False, method="first").astype(int)
        cols = ["pred_rank", "v2_rank", "title", "artist", "p_win", "fair_odds_win", "p_top5", "p_top10", "fair_odds_top10",
                "rd_votes", "rd_ballots", "is_aus2", "tj_cum", "sp_cum", "sp_best_rank"]
        out.head(100)[cols].to_csv(ROOT / f"reports/live_{stamp}_v3.csv", index=False)
        print(f"Reddit ballots so far: {int(out.rd_ballots.max())} (Reddit term {'on' if out.rd_ballots.max() >= MIN_BALLOTS else 'off'})")
        print(out.head(25)[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loyo")
