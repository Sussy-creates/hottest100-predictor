"""Build the song-level tables every feature is computed from.

Outputs (data/derived/):
  plays.parquet          one row per triple j play: Sydney date, recording, song_id
  tj_songs.csv           one row per song: recordings merged across radio edits / credit variants
  spotify_weekly.parquet Spotify AU top-200, weekly (Fri-Thu, week_end = Thursday), with song key
  matches.csv            countdown entries (ranks 1-200) -> triple j song_id and Spotify tracks

Holdout countdown entries are matched into data/holdout/matches_<year>.csv and never printed.
"""
from __future__ import annotations

import ast
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from h100.matching import find as _find, index as _index, pool as _pool  # noqa: E402
from h100.normalize import artist_tokens, artists_overlap, title_key, title_keys, version_of  # noqa: E402

DER, HOLD = ROOT / "data" / "derived", ROOT / "data" / "holdout"
HOLDOUT_YEAR = 2025


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


# ---------------------------------------------------------------- triple j
def load_plays() -> pd.DataFrame:
    rows = []
    for f in sorted((ROOT / "data" / "raw" / "abc_plays").glob("*/*.jsonl.gz")):
        for line in gzip.open(f, "rt", encoding="utf-8"):
            r = json.loads(line)
            names = [a["name"] for a in r["artists"] if a.get("name")] or [r.get("summary_artist") or ""]
            primary = [a["name"] for a in r["artists"] if a.get("type") == "primary"] or names
            rows.append({
                "played_utc": r["played_time"], "recording_id": r["recording_id"], "title": r["title"],
                "artist": ", ".join(primary), "all_artists": "|".join(names),
                "version": version_of(r.get("title"), r.get("summary_title"), r.get("release_title")),
                "release_format": r.get("release_format"),
            })
    p = pd.DataFrame(rows).drop_duplicates()
    t = pd.to_datetime(p["played_utc"], utc=True).dt.tz_convert("Australia/Sydney")
    p["date"] = t.dt.tz_localize(None).dt.normalize()
    p["played_syd"] = t.dt.tz_localize(None)
    p["tkey"] = p["title"].map(title_key)
    return p


def merge_recordings(p: pd.DataFrame) -> pd.DataFrame:
    """Recordings sharing a title key and version, with any artist in common, are one song."""
    rec = (p.groupby(["recording_id", "tkey", "version"])
             .agg(title=("title", "first"), artist=("artist", "first"), all_artists=("all_artists", "first"),
                  plays=("played_utc", "size"), first_play=("date", "min"), last_play=("date", "max"))
             .reset_index())
    rec["atok"] = rec["all_artists"].map(lambda s: artist_tokens(*s.split("|")))
    dsu = DSU()
    for (_, _), g in rec.groupby(["tkey", "version"]):
        items = list(zip(g["recording_id"], g["atok"]))
        for i, (ri, ai) in enumerate(items):
            dsu.find(ri)
            for rj, aj in items[i + 1:]:
                if artists_overlap(ai, aj):
                    dsu.union(ri, rj)
    rec["song_id"] = rec["recording_id"].map(dsu.find)
    return rec


# ---------------------------------------------------------------- Spotify
def spotify_weekly() -> pd.DataFrame:
    g = pd.read_parquet(ROOT / "data/raw/spotify_au/gonzalopezgil.parquet",
                        columns=["date", "rank", "uri", "track_name", "artist_names", "streams"])
    g["date"] = pd.to_datetime(g["date"])
    g["streams"] = pd.to_numeric(g["streams"], errors="coerce")
    g["rank"] = pd.to_numeric(g["rank"], errors="coerce")
    # Spotify chart weeks run Friday-Thursday; label each week by its Thursday.
    g["week_end"] = g["date"] + pd.to_timedelta((3 - g["date"].dt.weekday) % 7, unit="D")
    daily = (g.groupby(["week_end", "uri"])
               .agg(track_name=("track_name", "first"), artist_names=("artist_names", "first"),
                    streams=("streams", "sum"), best_rank=("rank", "min"), days_charted=("date", "nunique"))
               .reset_index())
    daily["source"] = "daily"

    j = pd.read_parquet(ROOT / "data/raw/spotify_au/jfreyberg__charts.parquet")
    j["week_end"] = pd.to_datetime(j["date"], format="mixed")
    j = j[j["week_end"] < daily["week_end"].min()]  # weekly source only where daily is missing
    j["artist_names"] = j["artists"].map(lambda s: "|".join(ast.literal_eval(s)) if isinstance(s, str) else "")
    weekly = pd.DataFrame({
        "week_end": j["week_end"], "uri": "spotify:track:" + j["track_id"], "track_name": j["name"],
        "artist_names": j["artist_names"], "streams": pd.to_numeric(j["streams"], errors="coerce"),
        "best_rank": pd.to_numeric(j["position"], errors="coerce"), "days_charted": 7, "source": "weekly",
    })
    s = pd.concat([weekly, daily], ignore_index=True)
    s["tkey"] = s["track_name"].map(title_key)
    s["version"] = s["track_name"].map(version_of)
    return s


# ---------------------------------------------------------------- countdown matching
def match_entries(results, rec, plays, sp, cal):
    songs = (rec.groupby("song_id")
               .agg(title=("title", "first"), version=("version", "first"),
                    atok=("atok", lambda x: frozenset().union(*x)),
                    first_play=("first_play", "min"), last_play=("last_play", "max"))
               .reset_index().rename(columns={"song_id": "ident"}))
    keys = songs["title"].map(title_keys)
    songs["k_short"], songs["k_full"] = keys.str[0], keys.str[1]
    s_idx = _index(songs, ["k_short", "k_full"])

    tracks = sp.drop_duplicates("uri")[["uri", "track_name", "artist_names", "version"]].rename(columns={"uri": "ident"})
    tkeys = tracks["track_name"].map(title_keys)
    tracks["k_short"], tracks["k_full"] = tkeys.str[0], tkeys.str[1]
    tracks["atok"] = tracks["artist_names"].map(lambda v: artist_tokens(*str(v).split("|")))
    span = sp.groupby("uri")["week_end"].agg(["min", "max"])
    tracks = tracks.join(span, on="ident")
    t_idx = _index(tracks, ["k_short", "k_full"])

    out = []
    for year, group in results.groupby("countdown_year"):
        c = cal.loc[cal["countdown_year"] == year].iloc[0]
        close = pd.Timestamp(str(c["voting_close_aedt"])[:10])
        start = pd.Timestamp(c["eligibility_start"]) - pd.Timedelta(days=90)
        late = close + pd.Timedelta(days=60)
        # Songs active around this countdown, including ones first played after close (zero pre-close airplay).
        s_pool, s_art = _pool(songs, "first_play", "last_play", start, late)
        t_pool, t_art = _pool(tracks, "min", "max", start, late)
        pre_plays = plays[(plays["date"] >= start) & (plays["date"] <= close)].groupby("song_id").size()
        sp_win = sp[(sp["week_end"] >= start) & (sp["week_end"] <= close)]  # complete weeks only: no post-close days
        sp_streams = sp_win.groupby("uri")["streams"].sum()
        sp_best = sp_win.groupby("uri")["best_rank"].min()
        for e in group.itertuples():
            ek, ver, at = set(title_keys(e.song)), version_of(e.song), artist_tokens(e.artist)
            hit, method = _find(ek, ver, at, s_idx, s_pool, s_art)
            ids = sorted({x.ident for x in hit})
            # Spotify pool is mainstream-heavy: a lone same-title track is usually another artist.
            thit, tmethod = _find(ek, ver, at, t_idx, t_pool, t_art, allow_title_only=False)
            uris = sorted({x.ident for x in thit})
            best = [sp_best[u] for u in uris if u in sp_best.index]
            out.append({
                "countdown_year": year, "rank": e.rank, "song": e.song, "artist": e.artist,
                "tj_song_ids": "|".join(ids), "tj_method": method,
                "tj_plays_pre_close": int(sum(pre_plays.get(i, 0) for i in ids)),
                "tj_first_play": min((x.first_play for x in hit), default=None),
                "spotify_uris": "|".join(uris), "spotify_method": tmethod,
                "spotify_streams_pre_close": int(sum(sp_streams.get(u, 0) for u in uris)),
                "spotify_best_rank_pre_close": min(best) if best else None,
            })
    return pd.DataFrame(out)


def main() -> None:
    DER.mkdir(parents=True, exist_ok=True)
    plays = load_plays()
    rec = merge_recordings(plays)
    plays = plays.merge(rec[["recording_id", "song_id"]], on="recording_id", how="left")
    plays[["played_syd", "date", "recording_id", "song_id", "title", "artist", "version"]].to_parquet(
        DER / "plays.parquet", index=False)
    lead = rec.sort_values("plays", ascending=False).drop_duplicates("song_id").set_index("song_id")
    songs = (rec.groupby("song_id")
               .agg(version=("version", "first"), tkey=("tkey", "first"), recordings=("recording_id", "nunique"),
                    plays=("plays", "sum"), first_play=("first_play", "min"), last_play=("last_play", "max"))
               .join(lead[["title", "artist"]])  # label each song by its most-played recording
               .reset_index())
    songs.to_csv(DER / "tj_songs.csv", index=False)
    print(f"triple j: {len(plays):,} plays, {rec['recording_id'].nunique():,} recordings -> {len(songs):,} songs")

    sp = spotify_weekly()
    sp.to_parquet(DER / "spotify_weekly.parquet", index=False)
    print(f"Spotify: {len(sp):,} track-weeks, {sp['uri'].nunique():,} tracks, "
          f"{sp['week_end'].min().date()} to {sp['week_end'].max().date()}")

    cal = pd.read_csv(ROOT / "config" / "countdowns.csv")
    train = pd.read_csv(DER / "results.csv")
    m = match_entries(train, rec, plays, sp, cal)
    m.to_csv(DER / "matches.csv", index=False)
    hold = pd.read_csv(HOLD / f"results_{HOLDOUT_YEAR}.csv")
    match_entries(hold, rec, plays, sp, cal).to_csv(HOLD / f"matches_{HOLDOUT_YEAR}.csv", index=False)
    print("training matches (triple j):", m.groupby("tj_method").size().to_dict())
    print("training matches (Spotify):", m.groupby("spotify_method").size().to_dict())


if __name__ == "__main__":
    main()
