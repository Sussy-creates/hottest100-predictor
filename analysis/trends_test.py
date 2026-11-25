"""LOYO test: does Google Trends artist interest add to core+aus (pairwise)? Two seed sets."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from harness import loyo, metrics, summary, CORE_FEATURES
from pairwise_fit import pw
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
t = pd.read_parquet(ROOT / "data/derived/trends_features.parquet")
f = f[f.snapshot == 0].merge(t, on=["countdown_year", "snapshot", "song_id"], how="left")
f["tr_have"] = f.tr_have.fillna(0)
base = CORE_FEATURES + ["is_aus"]
runs = {"core+aus pw": base, "+trends level": base + ["p_tr_level"],
        "+trends all": base + ["p_tr_level", "p_tr_recent", "p_tr_growth"]}
names = sys.argv[1:] or list(runs)
rows = []
for seeds in ((1, 2, 3, 4, 7), (11, 12, 13, 14, 15)):
    for name in names:
        p = loyo(f, runs[name], fitter=pw(seeds))
        p.to_parquet(ROOT / f"data/derived/loyo_preds_trends_{name.replace(' ', '_').replace('+', 'p')}_{seeds[0]}.parquet", index=False)
        m = metrics(p); s = summary(m); s["name"] = name; s["seeds"] = str(seeds)
        s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank)
        print(s, flush=True); rows.append(s)
pd.DataFrame(rows).to_csv(ROOT / "reports/trends_test.csv", index=False)
