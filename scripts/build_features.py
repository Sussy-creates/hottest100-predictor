"""Build snapshot features.

  python scripts/build_features.py train     -> data/derived/features.parquet (2015-2024, with labels)
  python scripts/build_features.py holdout   -> data/holdout/features_2025.parquet (no labels; only after rule-v1)
  python scripts/build_features.py live      -> data/live/features_<date>.parquet ("as if voting closed today")
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.features import build_year, spotify_tracks  # noqa: E402
from h100.matching import index  # noqa: E402

DER, HOLD = ROOT / "data" / "derived", ROOT / "data" / "holdout"


def load():
    plays = pd.read_parquet(DER / "plays.parquet", columns=["date", "song_id"])
    songs = pd.read_csv(DER / "tj_songs.csv", parse_dates=["first_play", "last_play"])
    sp = pd.read_parquet(DER / "spotify_weekly.parquet")
    tracks = spotify_tracks(sp)
    return plays, songs, sp, tracks, index(tracks, ["k_short", "k_full"])


def labels(matches: pd.DataFrame) -> pd.DataFrame:
    m = matches.dropna(subset=["tj_song_ids"]).copy()
    m["song_id"] = m["tj_song_ids"].str.split("|")
    return m.explode("song_id")[["countdown_year", "song_id", "rank"]].sort_values("rank").drop_duplicates(
        ["countdown_year", "song_id"])


def main(mode: str) -> None:
    cal = pd.read_csv(ROOT / "config" / "countdowns.csv")
    if mode == "live":
        today = pd.Timestamp.now(tz="Australia/Sydney").normalize().tz_localize(None)
        cal.loc[cal["set"] == "live", "voting_close_aedt"] = today.strftime("%Y-%m-%d")
    years = cal.loc[cal["set"] == {"train": "train", "holdout": "holdout", "live": "live"}[mode], "countdown_year"].tolist()
    plays, songs, sp, tracks, t_idx = load()
    out = []
    for y in years:
        f = build_year(y, cal.loc[cal["countdown_year"] == y].iloc[0], plays, songs, sp, tracks, t_idx)
        out.append(f)
        print(f"{y}: {f['song_id'].nunique()} candidates", flush=True)
    f = pd.concat(out, ignore_index=True)
    if mode == "train":
        lab = labels(pd.read_csv(DER / "matches.csv"))
        f = f.merge(lab, on=["countdown_year", "song_id"], how="left")
        f["rank"] = f["rank"].fillna(201).astype(int)
        f.to_parquet(DER / "features.parquet", index=False)
    elif mode == "holdout":
        f.to_parquet(HOLD / "features_2025.parquet", index=False)
    else:
        live = ROOT / "data" / "live"
        live.mkdir(parents=True, exist_ok=True)
        f.to_parquet(live / f"features_{today.date()}.parquet", index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "train")
