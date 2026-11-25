"""How much would a public vote sample add to the popularity model?

Uses 100 Warm Tunas' final predictions (votes counted from posted screenshots, 2016-2023) as a stand-in for
any 2026 vote sample (e.g. hottest100.com, Reddit threads, prediction playlists). Compares, per year:
  model v2 (LOYO scores) / Warm Tunas alone / blend = model z-score + w * vote z-score (w chosen year-out)
and repeats the blend with the vote sample thinned to smaller sizes, since a 2026 sample will be smaller.
Writes reports/warm_tunas_blend.txt.
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import numpy as np, pandas as pd
from history import lead


def tkey(s):
    s = re.sub(r"\s*[\(\[{].*?[\)\]}]", "", str(s).lower())
    return re.sub(r"[^a-z0-9]", "", s)


def fix_artist(a):  # "Avalanches, The" -> "The Avalanches"
    a = str(a)
    return "The " + a[:-5] if a.endswith(", The") else a


def attach(p: pd.DataFrame) -> pd.DataFrame:
    wt = pd.read_csv(ROOT / "data/raw/warm_tunas/predictions.csv")
    wt["k"] = wt.title.map(tkey) + "|" + wt.artist.map(fix_artist).map(lead)
    wt["k2"] = wt.title.map(tkey)
    p = p.copy()
    p["k"] = p.title.map(tkey) + "|" + p.artist.map(lead)
    p["k2"] = p.title.map(tkey)
    a = p.merge(wt[["countdown_year", "k", "wt_votes", "wt_rank"]], on=["countdown_year", "k"], how="left")
    # fall back to title-only within the year when the artist spelling differs and the title is unique on both sides
    miss = a.wt_votes.isna()
    u = wt.groupby(["countdown_year", "k2"]).filter(lambda g: len(g) == 1)
    pu = a[miss].groupby(["countdown_year", "k2"]).filter(lambda g: len(g) == 1)
    fb = pu[["countdown_year", "k2"]].reset_index().merge(u[["countdown_year", "k2", "wt_votes", "wt_rank"]], on=["countdown_year", "k2"]).set_index("index")
    a.loc[fb.index, ["wt_votes", "wt_rank"]] = fb[["wt_votes", "wt_rank"]].values
    return a


def topk(g, col, k=10):
    return set(g.sort_values(col, ascending=False).head(k).song_id)


def evaluate(a: pd.DataFrame, votes_col: str, ws=(0, .5, 1, 2, 3, 5, 8, 12, 20, 40)) -> pd.DataFrame:
    rows = []
    years = sorted(a.countdown_year.unique())
    def blend(g, w):
        v = np.log1p(g[votes_col].fillna(0))
        vz = (v - v.mean()) / (v.std() + 1e-9)
        return g.score + w * vz
    def score_year(g, col):
        act10 = set(g[g["rank"] <= 10].song_id); s = g.sort_values(col, ascending=False)
        return len(set(s.head(10).song_id) & act10), int(s.iloc[0]["rank"] == 1)
    for y in years:  # choose w on the other years, apply to y
        tr = a[a.countdown_year != y]
        best_w = max(ws, key=lambda w: sum(score_year(g.assign(b=blend(g, w)), "b")[0] + 0.5 * score_year(g.assign(b=blend(g, w)), "b")[1]
                                           for _, g in tr.groupby("countdown_year")))
        g = a[a.countdown_year == y].copy(); g["b"] = blend(g, best_w); g["v"] = g[votes_col].fillna(0)
        m10, m1 = score_year(g, "score"); v10, v1 = score_year(g, "v"); b10, b1 = score_year(g, "b")
        rows.append(dict(year=y, w=best_w, model_top10=m10, votes_top10=v10, blend_top10=b10, model_win=m1, votes_win=v1, blend_win=b1))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    p = pd.read_parquet(ROOT / "data/derived/loyo_preds_v2.parquet")
    p = p[p.countdown_year.between(2016, 2023)]
    a = attach(p)
    cov = a[a["rank"] <= 100].groupby("countdown_year").wt_votes.apply(lambda s: s.notna().mean())
    out = [f"Actual top-100 songs matched to a Warm Tunas count: {cov.round(2).to_dict()}"]
    tot = pd.read_csv(ROOT / "data/raw/warm_tunas/predictions.csv").groupby("countdown_year").wt_votes.sum()
    r = evaluate(a, "wt_votes")
    out.append("\nFull Warm Tunas sample (25k-67k votes counted per year)\n" + r.to_string(index=False))
    out.append(f"means: model {r.model_top10.mean():.2f}/{r.model_win.sum()} wins, votes {r.votes_top10.mean():.2f}/{r.votes_win.sum()}, blend {r.blend_top10.mean():.2f}/{r.blend_win.sum()}")
    rng = np.random.default_rng(0)
    for frac_name, n_votes in (("10,000 votes (~1,000 ballots)", 10000), ("3,000 votes (~300 ballots)", 3000), ("1,000 votes (~100 ballots)", 1000)):
        res = []
        for rep in range(5):
            b = a.copy()
            for y in b.countdown_year.unique():
                m = (b.countdown_year == y) & b.wt_votes.notna()
                frac = min(1.0, n_votes / tot[y])
                b.loc[m, "thin"] = rng.binomial(b.loc[m, "wt_votes"].astype(int), frac)
            res.append(evaluate(b, "thin"))
        rr = pd.concat(res)
        out.append(f"\nThinned to {frac_name}, 5 draws: votes alone {rr.votes_top10.mean():.2f} top10 / {rr.votes_win.mean()*8:.1f} wins of 8; "
                   f"blend {rr.blend_top10.mean():.2f} top10 / {rr.blend_win.mean()*8:.1f} wins of 8 (model alone {r.model_top10.mean():.2f} / {r.model_win.sum()})")
    txt = "\n".join(out)
    (ROOT / "reports/warm_tunas_blend.txt").write_text(txt)
    print(txt)
