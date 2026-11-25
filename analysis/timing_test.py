"""LOYO test: does release/peak timing add to core+aus with the pairwise objective?"""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from harness import loyo, metrics, summary, CORE_FEATURES
from pairwise_fit import pw
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
t = pd.read_parquet(ROOT / "data/derived/timing.parquet")
f = f[f.snapshot == 0].merge(t, on=["countdown_year", "song_id"], how="left")
base = CORE_FEATURES + ["is_aus"]
runs = {"core+aus pw (rerun)": base, "+age": base + ["p_tj_age"],
        "+timing": base + ["tj_first_ago", "tj_peak_ago", "sp_first_ago", "sp_peak_ago"]}
seeds = tuple(int(s) for s in sys.argv[1].split(",")) if len(sys.argv) > 1 else (1, 2, 3, 4, 7)
rows = []
for name, ft in runs.items():
    m = metrics(loyo(f, ft, fitter=pw(seeds))); s = summary(m); s["name"] = name; s["seeds"] = str(seeds)
    s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank)
    print(s, flush=True); rows.append(s)
pd.DataFrame(rows).to_csv(ROOT / f"reports/timing_test_{'-'.join(map(str, seeds))}.csv", index=False)
