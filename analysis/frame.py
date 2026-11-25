"""Analysis frame: all scored years (2015-2025) at every snapshot, with rank labels and Australian flag.
2025 was scored once under rule-v1; from here on it is used for diagnosis and as an 11th training year."""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.rule import add_derived

def load() -> pd.DataFrame:
    tr = pd.read_parquet(ROOT / "data/derived/features.parquet")
    ho = pd.read_parquet(ROOT / "data/holdout/features_2025.parquet")
    res = pd.read_csv(ROOT / "data/holdout/matches_2025.csv").dropna(subset=["tj_song_ids"])
    res["song_id"] = res["tj_song_ids"].str.split("|")
    lab = res.explode("song_id").groupby("song_id")["rank"].min()
    ho["rank"] = ho["song_id"].map(lab).fillna(201)
    f = add_derived(pd.concat([tr, ho], ignore_index=True))
    plays = pd.read_parquet(ROOT / "data/derived/plays.parquet", columns=["recording_id", "song_id"])
    top = plays.groupby(["song_id", "recording_id"]).size().reset_index(name="n").sort_values("n").drop_duplicates("song_id", keep="last")
    meta = pd.read_parquet(ROOT / "data/derived/recording_meta.parquet")
    aus = top.merge(meta, on="recording_id").set_index("song_id")["aus_any"]  # flag of the most-played recording
    f["is_aus"] = f["song_id"].map(aus).fillna(False).astype(float)
    return f

if __name__ == "__main__":
    f = load()
    f.to_parquet(ROOT / "data/derived/analysis_frame.parquet", index=False)
    g = f[f.snapshot == 0]
    print(g.groupby("countdown_year").agg(n=("song_id", "size"), top10=("rank", lambda r: (r <= 10).sum()),
          aus_share=("is_aus", "mean")).to_string())
    # validate Australian flag against Wikipedia country for ranked songs
    r = pd.concat([pd.read_csv(ROOT / "data/derived/results.csv"), pd.read_csv(ROOT / "data/holdout/results_2025.csv")])
    print(r.columns.tolist())
