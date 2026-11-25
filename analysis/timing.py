"""Release and peak timing at voting close (snapshot 0), per candidate.

Adds to the snapshot-0 rows of the analysis frame:
  tj_first_ago   days from first triple j play to close (same as tj_age)
  tj_peak_ago    days from the peak 7-day triple j play count to close
  sp_first_ago   days from first Spotify AU chart week to close (-1 = never charted)
  sp_peak_ago    days from peak Spotify AU stream week to close (-1 = never charted)
Writes data/derived/timing.parquet.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd  # noqa: E402
from h100.features import LEAD_IN, candidates, spotify_tracks  # noqa: E402
from h100.matching import find, index, pool  # noqa: E402
from h100.normalize import artist_tokens, title_keys  # noqa: E402

DER = ROOT / "data/derived"


def year_timing(cal_row, plays, songs, sp, tracks, t_idx):
    elig_s = pd.Timestamp(cal_row["eligibility_start"])
    close = pd.Timestamp(str(cal_row["voting_close_aedt"])[:10])
    start = elig_s - pd.Timedelta(days=LEAD_IN)
    cand = candidates(cal_row, plays, songs)
    cand["atok"] = cand["artist"].map(lambda a: artist_tokens(*str(a).split(", ")))
    ids = list(cand["song_id"])
    days = pd.date_range(start, close - pd.Timedelta(days=1), freq="D")
    win = plays[plays["song_id"].isin(ids) & (plays["date"] >= start) & (plays["date"] < close)]
    daily = (win.groupby(["song_id", "date"]).size().unstack(fill_value=0)
             .reindex(index=ids, columns=days, fill_value=0))
    roll7 = daily.T.rolling(7, min_periods=1).sum().T
    peak_day = roll7.idxmax(axis=1)

    t_pool, t_art = pool(tracks, "min", "max", start, close)
    pairs = []
    for r in cand.itertuples():
        hit, _ = find(set(title_keys(r.title)), r.version if isinstance(r.version, str) else "",
                      r.atok, t_idx, t_pool, t_art, allow_title_only=False)
        pairs += [(r.song_id, h.ident) for h in hit]
    link = pd.DataFrame(pairs, columns=["song_id", "uri"])
    spw = sp[(sp["week_end"] >= start) & (sp["week_end"] < close)].merge(link, on="uri")
    st = spw.groupby(["song_id", "week_end"])["streams"].sum().reset_index()
    sp_first = st.groupby("song_id")["week_end"].min()
    sp_peak = st.loc[st.groupby("song_id")["streams"].idxmax()].set_index("song_id")["week_end"]

    fp = cand.set_index("song_id")["first_play"]
    out = pd.DataFrame({"song_id": ids})
    out["countdown_year"] = int(cal_row["countdown_year"])
    out["tj_first_ago"] = (close - fp.reindex(ids)).dt.days.values
    out["tj_peak_ago"] = (close - peak_day.reindex(ids)).dt.days.values
    out["sp_first_ago"] = (close - sp_first.reindex(ids)).dt.days.fillna(-1).values
    out["sp_peak_ago"] = (close - sp_peak.reindex(ids)).dt.days.fillna(-1).values
    return out


if __name__ == "__main__":
    plays = pd.read_parquet(DER / "plays.parquet", columns=["date", "song_id"])
    songs = pd.read_csv(DER / "tj_songs.csv", parse_dates=["first_play", "last_play"])
    sp = pd.read_parquet(DER / "spotify_weekly.parquet")
    tracks = spotify_tracks(sp)
    t_idx = index(tracks, ["k_short", "k_full"])
    cal = pd.read_csv(ROOT / "config/countdowns.csv")
    rows = []
    for y in range(2015, 2026):
        rows.append(year_timing(cal.loc[cal.countdown_year == y].iloc[0], plays, songs, sp, tracks, t_idx))
        print(y, len(rows[-1]), flush=True)
    pd.concat(rows).to_parquet(DER / "timing.parquet", index=False)
