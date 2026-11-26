"""Leakage check for v3 win probabilities: choose the Reddit weight and the (tau, eps) calibration using the
other ten years only, then score the held-out year. Compare with the in-sample calibration (tuned on all 11 years)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "analysis")
import v2, v3
p2 = pd.read_parquet("data/derived/loyo_scores_v2.parquet")
rv = pd.read_parquet("data/derived/reddit_votes.parquet")
taus = np.round(np.exp(np.linspace(np.log(0.05), np.log(2), 24)), 4)
def fit_win(p):
    years = [g for _, g in p.groupby("countdown_year")]
    ll = {(t, e): sum(np.log((1 - e) * v2.win_probs(g.score.values, t)[(g["rank"] == 1).values].sum() + e / len(g)) for g in years)
          for t in taus for e in v2.EPS}
    return max(ll, key=ll.get)
def blend_w(w):
    old = v3.W; v3.W = w; b = v3.blend(p2, rv); v3.W = old; return b
WS = [0, 0.5, 1.0, 1.5, 2.0]
B = {w: blend_w(w) for w in WS}
def ll_win(b, yrs, t, e):
    return sum(np.log((1 - e) * v2.win_probs(g.score.values, t)[(g["rank"] == 1).values].sum() + e / len(g))
               for y, g in b.groupby("countdown_year") if y in yrs)
rows = []
full = B[1.0]; t_all, e_all = fit_win(full)
for y in sorted(full.countdown_year.unique()):
    others = [x for x in full.countdown_year.unique() if x != y]
    # choose w and (tau, eps) using other years only
    best = None
    for w in WS:
        b = B[w]; t, e = fit_win(b[b.countdown_year != y]); l = ll_win(b, others, t, e)
        if best is None or l > best[0]: best = (l, w, t, e)
    _, w, t, e = best
    g = B[w][B[w].countdown_year == y].copy()
    g["pw"] = (1 - e) * v2.win_probs(g.score.values, t) + e / len(g)
    g = g.sort_values("pw", ascending=False)
    gi = full[full.countdown_year == y].copy()
    gi["pw"] = (1 - e_all) * v2.win_probs(gi.score.values, t_all) + e_all / len(gi)
    gi = gi.sort_values("pw", ascending=False)
    top = g.iloc[0]
    rows.append(dict(year=y, ballots=int(g.rd_ballots.iloc[0]), w_chosen=w, pick=top.title, pw_yearout=round(top.pw, 2),
                     pw_insample=round(gi.iloc[0].pw, 2), rank=int(top["rank"]),
                     pick_votes=int(top.rd_votes), runnerup_votes=int(g.rd_votes.iloc[1:].max()), pick_v2rank=int(top.score_v2_rank) if "score_v2_rank" in g else None))
out = pd.DataFrame(rows).drop(columns="pick_v2rank").to_string(index=False); print(out); open("reports/v3_yearout_check.txt", "w").write(out + "\n")
