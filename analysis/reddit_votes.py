"""Vote counts from Reddit comments: how many distinct users list each candidate song before voting closes.

A comment counts as a ballot when it names at least MIN_SONGS candidate songs; each user counts once (latest
ballot before close). A song is named when its title appears as a whole phrase, and for short or common titles
the lead artist also appears in the comment. Writes data/derived/reddit_votes.parquet
(countdown_year, song_id, rd_votes, rd_ballots).
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
import pandas as pd
from history import SPLIT

MIN_SONGS = 3
COMMON = 8  # titles shorter than this (normalised) need the artist named too


def norm(s):
    s = re.sub(r"\s*[\(\[{].*?[\)\]}]", "", str(s).lower())
    s = re.sub(r"[‘’'`]", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def close_ts(cal, y):
    c = cal.loc[y, "voting_close_aedt"]
    if not isinstance(c, str):
        return pd.Timestamp.now(tz="UTC")
    t = pd.Timestamp(c if "T" in c else c + "T17:00")
    return t.tz_localize("Australia/Sydney").tz_convert("UTC")


def year_votes(y, cands, cal):
    path = ROOT / "data/raw/reddit" / f"{y}_comments.jsonl"
    if not path.exists():
        return None
    com = pd.read_json(path, lines=True)
    if com.empty:
        return None
    com["ts"] = pd.to_datetime(com.created_utc, unit="s", utc=True)
    com = com[(com.ts < close_ts(cal, y)) & com.body.notna() & ~com.author.isin(["[deleted]", "AutoModerator"])]
    pats = []
    dup = cands.title.map(norm).duplicated(keep=False).to_numpy()  # covers / same-name songs need the artist named
    for r, is_dup in zip(cands.itertuples(), dup):
        t = norm(r.title)
        if len(t.replace(" ", "")) < 3:
            continue
        a = norm(SPLIT.split(str(r.artist))[0]).removeprefix("the ")
        pats.append((r.song_id, re.compile(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])"), is_dup or len(t.replace(" ", "")) < COMMON, a))
    ballots = {}
    for c in com.sort_values("ts").itertuples():
        text = norm(c.body)
        hit = {sid for sid, p, need_artist, a in pats if p.search(text) and (not need_artist or (a and a in text))}
        if len(hit) >= MIN_SONGS:
            ballots[c.author] = hit  # latest ballot wins
    counts = pd.Series([s for h in ballots.values() for s in h]).value_counts()
    out = cands[["song_id"]].copy()
    out["countdown_year"] = y
    out["rd_votes"] = out.song_id.map(counts).fillna(0).astype(int)
    out["rd_ballots"] = len(ballots)
    return out


if __name__ == "__main__":
    cal = pd.read_csv(ROOT / "config/countdowns.csv").set_index("countdown_year")
    f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
    f = f[f.snapshot == 0]
    rows = []
    for y, g in f.groupby("countdown_year"):
        v = year_votes(y, g[["song_id", "title", "artist"]], cal)
        if v is not None:
            rows.append(v)
            top = v.merge(g[["song_id", "title", "artist", "rank"]], on="song_id").sort_values("rd_votes", ascending=False).head(10)
            print(y, "ballots", v.rd_ballots.iloc[0], "| top-10 by Reddit votes that made the actual top 10:", int((top["rank"] <= 10).sum()), flush=True)
    pd.concat(rows).to_parquet(ROOT / "data/derived/reddit_votes.parquet", index=False)
