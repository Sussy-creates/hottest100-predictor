"""Add-on features from archived + daily-collected YouTube AU and Shazam AU charts.

  python scripts/build_addons.py train     -> data/derived/addon_features.parquet, reports/addon_coverage.csv
  python scripts/build_addons.py holdout   -> data/holdout/addon_features_2025.parquet
  python scripts/build_addons.py live      -> data/live/addon_features_<date>.parquet
"""
from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.addon import chart_features  # noqa: E402
from h100.charts import load_captures, parse_kworb, parse_shazam_old  # noqa: E402

WB, DAILY = ROOT / "data/raw/wayback", ROOT / "data/raw/daily"


def daily_folder(folder: Path, parser) -> pd.DataFrame:
    out = []
    for f in sorted(folder.glob("*.html.gz")):
        df = parser(gzip.decompress(f.read_bytes()).decode("utf-8", "replace"))
        if len(df):
            df["captured"] = pd.Timestamp(f.name[:10])
            out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def parse_shazam_csv(text: str) -> pd.DataFrame:
    lines = [l for l in text.lstrip("﻿").splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if l.lower().startswith("rank,")), None)
    if start is None:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    return df.rename(columns=str.lower)[["rank", "artist", "title"]].assign(value=None)


def charts() -> dict[str, pd.DataFrame]:
    yt = [load_captures(WB / "kworb_youtube_au_daily", parse_kworb), load_captures(WB / "kworb_youtube_au_weekly", parse_kworb),
          daily_folder(DAILY / "kworb_youtube_au_daily", parse_kworb), daily_folder(DAILY / "kworb_youtube_au_weekly", parse_kworb)]
    sz = [load_captures(WB / "kworb_shazam_au", parse_kworb), load_captures(WB / "shazam_top100_au_old", parse_shazam_old),
          load_captures(WB / "shazam_au_top_100_old", parse_shazam_old), daily_folder(DAILY / "kworb_shazam_au", parse_kworb),
          daily_folder(DAILY / "shazam_top200_au_csv", parse_shazam_csv)]
    return {"yt": pd.concat([d for d in yt if len(d)], ignore_index=True),
            "sz": pd.concat([d for d in sz if len(d)], ignore_index=True)}


def main(mode: str) -> None:
    cal = pd.read_csv(ROOT / "config/countdowns.csv")
    if mode == "train":
        f, dest = pd.read_parquet(ROOT / "data/derived/features.parquet"), ROOT / "data/derived/addon_features.parquet"
    elif mode == "holdout":
        f, dest = pd.read_parquet(ROOT / "data/holdout/features_2025.parquet"), ROOT / "data/holdout/addon_features_2025.parquet"
    else:
        latest = sorted((ROOT / "data/live").glob("features_*.parquet"))[-1]
        f, dest = pd.read_parquet(latest), ROOT / "data/live" / latest.name.replace("features_", "addon_features_")
        cal.loc[cal["set"] == "live", "voting_close_aedt"] = latest.stem.replace("features_", "")
    c = charts()
    for k, v in c.items():
        print(f"{k}: {len(v):,} chart rows from {v['captured'].dt.normalize().nunique()} days "
              f"({v['captured'].min().date()} to {v['captured'].max().date()})")
    a = chart_features(f, c["yt"], cal, "yt").merge(
        chart_features(f, c["sz"], cal, "sz"), on=["countdown_year", "snapshot", "song_id"])
    a.to_parquet(dest, index=False)
    if mode == "train":
        cov = a[a["snapshot"] == 0].groupby("countdown_year")[["yt_captures", "sz_captures"]].first()
        cov.to_csv(ROOT / "reports/addon_coverage.csv")
        print(cov.to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "train")
