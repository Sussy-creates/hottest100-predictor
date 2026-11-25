"""Drop candidates that already placed (top 200) in the previous countdown; they can't place again.

Adds prev_rank to the snapshot rows and runs the LOYO comparison (core+aus, pairwise, two seed sets).
"""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from history import lead


def tk(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*[\(\[].*?[\)\]]", "", str(s).lower()))


def prev_rank(f: pd.DataFrame) -> pd.Series:
    h = pd.read_csv(ROOT / "data/derived/results_history.csv")
    prev = {(y + 1, tk(s) + "|" + lead(a)): r for y, s, a, r in zip(h.countdown_year, h.song, h.artist, h["rank"])}
    return pd.Series([prev.get((y, tk(t) + "|" + lead(a))) for y, t, a in zip(f.countdown_year, f.title, f.artist)], index=f.index)


if __name__ == "__main__":
    from harness import loyo, metrics, summary, CORE_FEATURES
    from pairwise_fit import pw
    f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
    f = f[f.snapshot == 0].copy()
    f["prev_rank"] = prev_rank(f)
    print(f[f.prev_rank.notna() & f["rank"].le(200)][["countdown_year", "title", "artist", "prev_rank", "rank"]])
    g = f[f.prev_rank.isna()]
    rows = []
    for seeds in ((1, 2, 3, 4, 7), (11, 12, 13, 14, 15)):
        m = metrics(loyo(g, CORE_FEATURES + ["is_aus"], fitter=pw(seeds))); s = summary(m)
        s["name"] = "core+aus pw, prev-countdown filter"; s["seeds"] = str(seeds)
        s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank)
        print(s, flush=True); rows.append(s)
    pd.DataFrame(rows).to_csv(ROOT / "reports/prev_filter_test.csv", index=False)
