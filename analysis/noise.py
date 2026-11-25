"""How much do LOYO metrics move from seeds alone? Re-run core and core+aus with a different seed set."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import pandas as pd
from harness import loyo, metrics, summary, CORE_FEATURES
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
for name, feats in [("core", CORE_FEATURES), ("core+aus", CORE_FEATURES + ["is_aus"])]:
    m = metrics(loyo(f, feats, seeds=(11, 12, 13, 14, 15)))
    s = summary(m); s["name"] = name + " seeds11-15"; s["per_year_top10"] = " ".join(map(str, m.top10)); print(s, flush=True)
