"""Leave-one-year-out evaluation of a model spec, at every snapshot (training years only).

  python scripts/loyo_model.py config/model_v1.json [--addons]
Writes reports/loyo_<spec>.csv (per year and snapshot) and prints a summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.model import fit, predict  # noqa: E402
from h100.rule import add_derived, evaluate  # noqa: E402


def main(spec_path: str, with_addons: bool, years: list[int] | None = None) -> pd.DataFrame:
    spec = json.loads((ROOT / spec_path).read_text())
    feats = spec["features"]
    f = add_derived(pd.read_parquet(ROOT / "data/derived/features.parquet"))
    if with_addons:
        f = f.merge(pd.read_parquet(ROOT / "data/derived/addon_features.parquet"),
                    on=["countdown_year", "snapshot", "song_id"], how="left")
    rows = []
    for snap in (0, 30, 60, 90):
        g = f[f["snapshot"] == snap]
        if years:
            g = g[g["countdown_year"].isin(years)]

        def scorer(y, frame):
            models = fit(f[(f["snapshot"] == 0) & (f["countdown_year"] != y)], feats)
            return predict(models, frame, feats)

        r = evaluate(g, scorer)
        r["snapshot"] = snap
        rows.append(r)
    res = pd.concat(rows, ignore_index=True)
    name = Path(spec_path).stem
    res.to_csv(ROOT / "reports" / f"loyo_{name}.csv", index=False)
    s = res.groupby("snapshot").agg(mean_top10=("top10_overlap", "mean"), mean_top5=("top5_overlap", "mean"),
                                    winner_hit=("winner_hit", "sum"), winner_top3=("winner_top3", "sum"),
                                    median_winner_rank=("winner_pred_rank", "median"),
                                    spearman_top10=("top10_spearman", "mean"))
    print(name); print(s.round(2).to_string())
    return res


if __name__ == "__main__":
    main(sys.argv[1], "--addons" in sys.argv)
