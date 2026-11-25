import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import pandas as pd
from harness import loyo, metrics, summary, CORE_FEATURES
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
p = loyo(f, CORE_FEATURES)
p.to_parquet(ROOT / "data/derived/loyo_preds_core.parquet", index=False)
m = metrics(p); print(m.to_string(index=False)); print(summary(m))
