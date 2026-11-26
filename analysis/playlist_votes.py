"""How many public vote / prediction playlists list each candidate song (data/raw/spotify_playlists snapshots).

For each year, use the newest snapshot taken on or before voting close (live year: the newest snapshot). Keep
playlists whose name says they are someone's votes, shortlist or predictions for that year (not decade or
all-time lists, not the official countdown) with at most MAX_TRACKS tracks. A song is listed when a track's
title key matches and the track artists include the candidate's lead artist. Each playlist owner counts once.
Writes data/derived/playlist_votes.parquet (countdown_year, song_id, pl_votes, pl_lists).

Past years' playlists were downloaded long after their countdowns, so they may have been edited after the
results: treat their numbers as a rough check only.
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import pandas as pd
from history import lead
from reddit_votes import close_ts

MAX_TRACKS = 120
VOTEY = re.compile(r"vote|my |mine|shortlist|short list|prediction|predict|picks|guess", re.I)
NOT = re.compile(r"decade|best of|all ?time|every year|\d{4}\s*[-–]\s*\d{4}|official|australian songs|like a version", re.I)


def tkey(s):
    s = re.sub(r"\s*[\(\[{].*?[\)\]}]", "", str(s).lower())
    s = re.sub(r"\s+-\s+.*$", "", s)  # "Song - Radio Edit"
    return re.sub(r"[^a-z0-9]", "", s)


def akey(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower()).removeprefix("the")


def snapshot_for(y, cal):
    snaps = sorted(p for p in (ROOT / "data/raw/spotify_playlists").glob("*") if p.is_dir())
    cut = close_ts(cal, y).tz_convert("Australia/Sydney").date().isoformat()
    ok = [p for p in snaps if p.name <= cut]
    if not ok and y < 2026:  # past years: only post-countdown snapshots exist (rough check only)
        ok = snaps
    return ok[-1] if ok else None


def year_votes(y, cands, cal):
    d = snapshot_for(y, cal)
    if d is None or not (d / "tracks.jsonl").exists():
        return None
    s = pd.read_json(d / "search.jsonl", lines=True)
    t = pd.read_json(d / "tracks.jsonl", lines=True)
    s = s[s.year == y].drop_duplicates("id")
    s = s[s.name.fillna("").str.contains(str(y)) & s.name.fillna("").str.contains(VOTEY) & ~s.name.fillna("").str.contains(NOT)
          & (s.n_tracks.fillna(0) <= MAX_TRACKS)]
    s = s.drop_duplicates("owner")
    t = t[t.playlist_id.isin(s.id)].copy()
    if t.empty:
        return None
    t["k"] = t.title.map(tkey)
    t["a"] = t.artists.fillna("").map(lambda x: {akey(a) for a in str(x).split(",")})
    c = cands.copy(); c["k"] = c.title.map(tkey); c["a"] = c.artist.map(lambda x: akey(lead(x)))
    m = t.merge(c[["song_id", "k", "a"]], on="k", suffixes=("_t", "_c"))
    m = m[[ac in at for at, ac in zip(m.a_t, m.a_c)]]
    counts = m.drop_duplicates(["playlist_id", "song_id"]).groupby("song_id").size()
    out = cands[["song_id"]].copy()
    out["countdown_year"] = y
    out["pl_votes"] = out.song_id.map(counts).fillna(0).astype(int)
    out["pl_lists"] = t.playlist_id.nunique()
    return out


if __name__ == "__main__":
    cal = pd.read_csv(ROOT / "config/countdowns.csv").set_index("countdown_year")
    f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
    f = f[f.snapshot == 0]
    rows = []
    for y, g in f.groupby("countdown_year"):
        v = year_votes(y, g[["song_id", "title", "artist"]], cal)
        if v is None:
            continue
        rows.append(v)
        top = v.merge(g[["song_id", "title", "artist", "rank"]], on="song_id").sort_values("pl_votes", ascending=False).head(10)
        print(y, "playlists", v.pl_lists.iloc[0], "| playlist top 10 in actual top 10:", int((top["rank"] <= 10).sum()), flush=True)
    if rows:
        pd.concat(rows).to_parquet(ROOT / "data/derived/playlist_votes.parquet", index=False)
