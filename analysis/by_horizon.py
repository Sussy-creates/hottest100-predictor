"""How good is the model at T-60/-30/-0 days before close? Train v2 on other years' close snapshots, score the
held-out year's earlier snapshot; add Reddit ballots posted up to the same cutoff (v3 rule: >=50 ballots, w=1)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "analysis"); sys.path.insert(0, "src")
import v2, v3, reddit_votes as rvm
from aus_fix import aus_fixed; from prev_filter import prev_rank; from pairwise_fit import pw
f = pd.read_parquet("data/derived/analysis_frame.parquet")
f["is_aus2"] = aus_fixed(f); f["prev_rank"] = prev_rank(f); f = f[f.prev_rank.isna()]
cal = pd.read_csv("config/countdowns.csv").set_index("countdown_year")
fit = pw((1, 2, 3, 4, 7))
rows = []
for y in range(2015, 2026):
    tr = f[(f.snapshot == 0) & (f.countdown_year != y)]
    for snap, cut in ((60, 60), (30, 30), (30, 14), (0, 0)):
        te = f[(f.snapshot == snap) & (f.countdown_year == y)].copy()
        te["score"] = fit(tr, te, v2.FEATURES)
        c2 = cal.copy()
        t = rvm.close_ts(cal, y) - pd.Timedelta(days=cut)
        c2.loc[y, "voting_close_aedt"] = t.tz_convert("Australia/Sydney").strftime("%Y-%m-%dT%H:%M")
        v = rvm.year_votes(y, te[["song_id", "title", "artist"]], c2)
        b = v3.blend(te, v) if v is not None else te.assign(rd_ballots=0)
        b = b.sort_values("score", ascending=False)
        p2 = te.sort_values("score", ascending=False)
        top10 = set(f[(f.snapshot == 0) & (f.countdown_year == y) & (f["rank"] <= 10)].song_id)
        rows.append(dict(year=y, days_before=cut, ballots=int(b.rd_ballots.max() if "rd_ballots" in b else 0),
                         v2_win=int(p2["rank"].iloc[0] == 1), v2_top10=len(set(p2.song_id.head(10)) & top10),
                         v3_win=int(b["rank"].iloc[0] == 1), v3_top10=len(set(b.song_id.head(10)) & top10)))
r = pd.DataFrame(rows)
print(r.to_string(index=False))
print(r.groupby("days_before").agg(ballots=("ballots", "median"), v2_wins=("v2_win", "sum"), v2_top10=("v2_top10", "mean"),
                                    v3_wins=("v3_win", "sum"), v3_top10=("v3_top10", "mean")).round(2).sort_index(ascending=False).to_string())
