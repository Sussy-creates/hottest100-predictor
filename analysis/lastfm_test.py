"""Does the Last.fm Australian listener panel add to the model?

Matches data/raw/lastfm/<year>.csv (per-song panel listeners and plays in the 120 days before close) to each year's
candidates by title key + lead artist, writes data/derived/lastfm_features.parquet, then tests
  blend = model z-score + w * z(log1p panel listeners), w chosen year-out (as analysis/warm_tunas.py)
on top of v2 alone and on top of v3 (v2 + Reddit ballots). Writes reports/lastfm_blend.txt.
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import numpy as np, pandas as pd
from history import lead
from warm_tunas import evaluate


def tkey(s):
    s = re.sub(r"\s*[\(\[{].*?[\)\]}]", "", str(s).lower())
    s = re.sub(r"\s+-\s+.*$", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def akey(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower()).removeprefix("the")


def attach(cands: pd.DataFrame, lf: pd.DataFrame) -> pd.DataFrame:
    lf = lf.copy(); lf["k"] = lf.track.map(tkey) + "|" + lf.artist.map(lambda a: akey(lead(a)))
    lf = lf.groupby(["countdown_year", "k"], as_index=False).agg(lf_listeners=("listeners", "sum"), lf_plays=("plays", "sum"),
                                                                  lf_panel=("panel_active", "max"))
    c = cands.copy(); c["k"] = c.title.map(tkey) + "|" + c.artist.map(lambda a: akey(lead(a)))
    out = c.merge(lf, on=["countdown_year", "k"], how="left").drop(columns="k")
    out["lf_panel"] = out.groupby("countdown_year").lf_panel.transform("max")
    return out


def load_lastfm(years):
    fs = [ROOT / f"data/raw/lastfm/{y}.csv" for y in years]
    return pd.concat([pd.read_csv(f) for f in fs if f.exists()])


if __name__ == "__main__":
    import v3
    p2 = pd.read_parquet(ROOT / "data/derived/loyo_scores_v2.parquet")
    lf = load_lastfm(range(2015, 2026))
    a = attach(p2, lf)
    a[["countdown_year", "song_id", "lf_listeners", "lf_plays", "lf_panel"]].to_parquet(ROOT / "data/derived/lastfm_features.parquet", index=False)
    out = ["Panel members active per year: " + str(a.groupby("countdown_year").lf_panel.max().to_dict()),
           "Actual top-10 songs found in the panel: " + str(a[a["rank"] <= 10].groupby("countdown_year").lf_listeners.apply(lambda s: int(s.notna().sum())).to_dict())]
    yrs = sorted(a.countdown_year[a.lf_panel.notna()].unique())
    for name, base in (("v2", a), ("v3 (v2 + Reddit)", attach(v3.blend(p2, pd.read_parquet(ROOT / "data/derived/reddit_votes.parquet")), lf))):
        b = base[base.countdown_year.isin(yrs)]
        r = evaluate(b, "lf_listeners")
        out.append(f"\nOn top of {name}:\n" + r.to_string(index=False) +
                   f"\nmeans: model {r.model_top10.mean():.2f} top10 / {r.model_win.sum()} wins; Last.fm alone {r.votes_top10.mean():.2f} / {r.votes_win.sum()};"
                   f" blend {r.blend_top10.mean():.2f} / {r.blend_win.sum()} (of {len(r)}); better {(r.blend_top10 > r.model_top10).sum()} yrs, worse {(r.blend_top10 < r.model_top10).sum()}")
    txt = "\n".join(out); (ROOT / "reports/lastfm_blend.txt").write_text(txt); print(txt)
