"""Does a Reddit ballot count improve model v2? Blend = v2 LOYO z-score + w * z(log1p Reddit votes), w chosen
year-out (same method as analysis/warm_tunas.py). Writes reports/reddit_blend.txt."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import numpy as np, pandas as pd
from warm_tunas import evaluate

if __name__ == "__main__":
    p = pd.read_parquet(ROOT / "data/derived/loyo_preds_v2.parquet")
    v = pd.read_parquet(ROOT / "data/derived/reddit_votes.parquet")
    a = p.merge(v, on=["countdown_year", "song_id"], how="left")
    years = [int(y) for y in sys.argv[1:]] or list(range(2016, 2026))
    a = a[a.countdown_year.isin(years)]
    r = evaluate(a, "rd_votes")
    r["ballots"] = r.year.map(v.groupby("countdown_year").rd_ballots.first())
    def logrank(col):  # mean log rank of the actual top 10 under each ordering
        out = []
        for _, g in a.groupby("countdown_year"):
            pr = g[col].rank(ascending=False, method="first")
            out.append(np.log(pr[g["rank"] <= 10]).mean())
        return np.mean(out)
    txt = (r.to_string(index=False) +
           f"\nmeans: model {r.model_top10.mean():.2f} top10 / {r.model_win.sum()} wins; Reddit alone {r.votes_top10.mean():.2f} / {r.votes_win.sum()};"
           f" blend {r.blend_top10.mean():.2f} / {r.blend_win.sum()} (of {len(r)}). Blend better in {(r.blend_top10 > r.model_top10).sum()} years, worse in {(r.blend_top10 < r.model_top10).sum()}.")
    (ROOT / "reports/reddit_blend.txt").write_text(txt)
    print(txt)
