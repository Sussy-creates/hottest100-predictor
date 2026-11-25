"""Train the frozen model(s) on all training years and score the holdout or the live year.

  python scripts/score.py holdout   # refuses to run unless tag rule-v1 exists and is an ancestor of HEAD
  python scripts/score.py live      # scores data/live/features_<latest>.parquet
  Optional third argument: one spec name (primary / with_addons); default is both.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.model import fit, predict  # noqa: E402
from h100.rule import add_derived  # noqa: E402

SPECS = {"primary": "config/model_v1.json", "with_addons": "config/model_v1_addons.json"}


def frozen() -> bool:
    ok = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", "rule-v1", "HEAD"])
    return ok.returncode == 0


def addons(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    if not path.exists():
        return frame
    a = pd.read_parquet(path)
    return frame.merge(a, on=["countdown_year", "snapshot", "song_id"], how="left")


def rank_with(spec_name: str, train: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    spec = json.loads((ROOT / SPECS[spec_name]).read_text())
    feats = spec["features"]
    models = fit(train[train["snapshot"] == 0], feats)
    t = target.copy()
    t["score"] = predict(models, t, feats)
    t = t.sort_values("score", ascending=False)
    t["pred_rank"] = range(1, len(t) + 1)
    return t


def main(mode: str, only: str | None = None) -> None:
    specs = [only] if only else list(SPECS)
    train = add_derived(pd.read_parquet(ROOT / "data/derived/features.parquet"))
    train = addons(train, ROOT / "data/derived/addon_features.parquet")
    out = ROOT / "reports"
    if mode == "holdout":
        if not frozen():
            sys.exit("rule-v1 tag missing or not an ancestor of HEAD: freeze before scoring the holdout")
        tgt = add_derived(pd.read_parquet(ROOT / "data/holdout/features_2025.parquet"))
        tgt = addons(tgt[tgt["snapshot"] == 0], ROOT / "data/holdout/addon_features_2025.parquet")
        res = pd.read_csv(ROOT / "data/holdout/matches_2025.csv").dropna(subset=["tj_song_ids"])
        res["song_id"] = res["tj_song_ids"].str.split("|")
        lab = res.explode("song_id")[["song_id", "rank", "song", "artist"]].rename(
            columns={"song": "actual_song", "artist": "actual_artist"})
        for name in specs:
            r = rank_with(name, train, tgt).merge(lab, on="song_id", how="left")
            r.to_csv(out / f"holdout_2025_{name}.csv", index=False)
    else:
        latest = sorted((ROOT / "data/live").glob("features_*.parquet"))[-1]
        tgt = add_derived(pd.read_parquet(latest))
        tgt = addons(tgt[tgt["snapshot"] == 0], ROOT / "data/live" / latest.name.replace("features_", "addon_features_"))
        for name in specs:
            r = rank_with(name, train, tgt)
            r.head(100).to_csv(out / f"live_{latest.stem.replace('features_', '')}_{name}.csv", index=False)
        print(f"scored {latest.name}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
