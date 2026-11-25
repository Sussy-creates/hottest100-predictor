"""Artists to fetch Google Trends for: lead artists of each year's top-500 candidates.

2015-2025 use the out-of-sample LOYO ranking (core+aus, pairwise); 2026 uses the latest live ranking.
Writes data/derived/trends_targets.csv (countdown_year, window_start, window_end, artist)
and data/derived/release_targets.csv (the same top-500 songs, for the release-date lookup).
"""
import re, sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOP = 500
LOOKBACK = 150  # days of daily history before close (covers T-120 plus a pre-window)
SPLIT = re.compile(r"\s+(?:featuring|feat\.?|ft\.?|with|x|vs\.?|&|and)\s+|,\s*|\s+/\s+", re.I)

def lead_name(a: str) -> str:
    return SPLIT.split(str(a))[0].strip()

cal = pd.read_csv(ROOT / "config/countdowns.csv").set_index("countdown_year")
p = pd.read_parquet(ROOT / "data/derived/loyo_preds_core+aus_pairwise.parquet")
# Live year: rank every snapshot-0 candidate with the core pairwise model trained on all 11 years.
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
from harness import CORE_FEATURES  # noqa: E402
from pairwise_fit import pw  # noqa: E402
f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
live = pd.read_parquet(sorted((ROOT / "data/live").glob("features_*.parquet"))[-1])
from h100.rule import add_derived  # noqa: E402
live = add_derived(live[live.snapshot == 0])
live["score"] = pw()(f[f.snapshot == 0], live, CORE_FEATURES)
live["pred_rank"] = live["score"].rank(ascending=False, method="first")
cols = ["countdown_year", "song_id", "title", "artist", "pred_rank"]
p = pd.concat([p[cols], live[cols]])
# Songs for the release-date lookup (same top-500 set).
p[p.pred_rank <= TOP][cols[:4]].to_csv(ROOT / "data/derived/release_targets.csv", index=False)
rows = []
for y, g in p[p.pred_rank <= TOP].groupby("countdown_year"):
    close = cal.loc[y, "voting_close_aedt"]
    end = date.fromisoformat(str(close)[:10]) if isinstance(close, str) else date.today()
    start = end - timedelta(days=LOOKBACK)
    for a in sorted({lead_name(a) for a in g.artist}):
        rows.append((y, start.isoformat(), (end - timedelta(days=1)).isoformat(), a))
out = pd.DataFrame(rows, columns=["countdown_year", "window_start", "window_end", "artist"])
out.to_csv(ROOT / "data/derived/trends_targets.csv", index=False)
print(out.groupby("countdown_year").size().to_string(), "\ntotal", len(out))
