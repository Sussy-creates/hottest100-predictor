"""Snapshot features for one countdown year.

Every feature at snapshot T uses only data dated before T, where T = voting close minus d days
(T for d=0 is the start of the close day, so nothing from close day itself is used).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .matching import find, index, pool
from .normalize import artist_tokens, title_keys

SNAPSHOTS = (120, 90, 60, 30, 0)
LEAD_IN = 90            # days of airplay before eligibility start that count towards trajectory
LATE_FIRST_PLAY = 14    # songs first played up to this many days after eligibility end stay candidates
MIN_PLAYS = 5           # pre-close plays needed to be a candidate
LIFTOFF = 10            # plays in 7 days that count as "on rotation"
MIN_PEAK7 = 3           # a candidate must have had at least this many plays in some 7-day stretch
                        # (drops occasional catalogue plays; keeps every training top-10 song)

RAW = ["tj_cum", "tj_peak7", "tj_last28", "tj_accel", "tj_fade", "tj_age", "tj_since_liftoff",
       "tj_artist_share", "tj_artist_songs", "tj_artist_plays",
       "sp_cum", "sp_best_rank", "sp_weeks", "sp_last4", "sp_accel", "sp_charted", "is_lav"]
# Higher is better for the percentile of every feature except these, where lower is better.
LOWER_IS_BETTER = {"sp_best_rank", "tj_artist_songs"}


def spotify_tracks(sp: pd.DataFrame) -> pd.DataFrame:
    t = sp.drop_duplicates("uri")[["uri", "track_name", "artist_names", "version"]].rename(columns={"uri": "ident"})
    k = t["track_name"].map(title_keys)
    t["k_short"], t["k_full"] = k.str[0], k.str[1]
    t["atok"] = t["artist_names"].map(lambda v: artist_tokens(*str(v).split("|")))
    span = sp.groupby("uri")["week_end"].agg(["min", "max"])
    return t.join(span, on="ident")


def candidates(cal_row, plays: pd.DataFrame, songs: pd.DataFrame) -> pd.DataFrame:
    elig_s, elig_e = pd.Timestamp(cal_row["eligibility_start"]), pd.Timestamp(cal_row["eligibility_end"])
    close = pd.Timestamp(str(cal_row["voting_close_aedt"])[:10])
    start = elig_s - pd.Timedelta(days=LEAD_IN)
    win = plays[(plays["date"] >= start) & (plays["date"] < close)]
    n = win.groupby("song_id").size()
    s = songs.set_index("song_id")
    keep = s[(s["first_play"] >= elig_s) & (s["first_play"] <= elig_e + pd.Timedelta(days=LATE_FIRST_PLAY))
             & (s["version"].fillna("") != "live")].index
    ids = n[(n >= MIN_PLAYS) & n.index.isin(keep)].index
    return s.loc[ids].reset_index()


def build_year(year: int, cal_row, plays: pd.DataFrame, songs: pd.DataFrame,
               sp: pd.DataFrame, tracks: pd.DataFrame, t_idx) -> pd.DataFrame:
    elig_s = pd.Timestamp(cal_row["eligibility_start"])
    close = pd.Timestamp(str(cal_row["voting_close_aedt"])[:10])
    start = elig_s - pd.Timedelta(days=LEAD_IN)
    cand = candidates(cal_row, plays, songs)
    cand["atok"] = cand["artist"].map(lambda a: artist_tokens(*str(a).split(", ")))
    ids = list(cand["song_id"])

    # Daily play matrix: song x day, start .. close-1.
    days = pd.date_range(start, close - pd.Timedelta(days=1), freq="D")
    win = plays[plays["song_id"].isin(ids) & (plays["date"] >= start) & (plays["date"] < close)]
    daily = (win.groupby(["song_id", "date"]).size().unstack(fill_value=0)
                .reindex(index=ids, columns=days, fill_value=0))
    roll7 = daily.T.rolling(7, min_periods=1).sum().T

    # Spotify: candidate -> matched tracks (artist overlap required) -> weekly streams.
    t_pool, t_art = pool(tracks, "min", "max", start, close)
    uri_of = {}
    for r in cand.itertuples():
        hit, _ = find(set(title_keys(r.title)), r.version if isinstance(r.version, str) else "",
                      r.atok, t_idx, t_pool, t_art, allow_title_only=False)
        uri_of[r.song_id] = {h.ident for h in hit}
    pairs = [(sid, u) for sid, us in uri_of.items() for u in us]
    link = pd.DataFrame(pairs, columns=["song_id", "uri"]) if pairs else pd.DataFrame(columns=["song_id", "uri"])
    spw = sp[(sp["week_end"] >= start) & (sp["week_end"] < close)].merge(link, on="uri")
    sp_streams = spw.groupby(["song_id", "week_end"])["streams"].sum().unstack(fill_value=0)
    sp_rank = spw.groupby(["song_id", "week_end"])["best_rank"].min().unstack()

    # Artist groupings for vote-splitting (a song counts towards every artist credited on it).
    tok_songs = defaultdict(list)
    for r in cand.itertuples():
        for t in r.atok:
            tok_songs[t].append(r.song_id)
    first_play = cand.set_index("song_id")["first_play"]
    is_lav = cand.set_index("song_id")["version"].fillna("").eq("lav").astype(int)

    rows = []
    for d in SNAPSHOTS:
        T = close - pd.Timedelta(days=d)
        cols = days[days < T]
        if len(cols) == 0:
            continue
        cum = daily[cols].sum(axis=1)
        r7 = roll7[cols]
        last28 = daily[cols[-28:]].sum(axis=1)
        prev28 = daily[cols[-56:-28]].sum(axis=1) if len(cols) > 28 else 0 * last28
        peak7 = r7.max(axis=1)
        now7 = r7[cols[-1]]
        on_rot = r7.ge(LIFTOFF)
        lift_day = on_rot.idxmax(axis=1).where(on_rot.any(axis=1))
        since_lift = (T - pd.to_datetime(lift_day)).dt.days
        age = (T - first_play.reindex(ids)).dt.days.clip(lower=0)

        art_plays = {t: cum.reindex(s_ids).sum() for t, s_ids in tok_songs.items()}
        art_songs = {t: int((cum.reindex(s_ids) >= MIN_PLAYS).sum()) for t, s_ids in tok_songs.items()}
        a_tot = cand.set_index("song_id")["atok"].map(lambda ts: max((art_plays[t] for t in ts), default=0))
        a_n = cand.set_index("song_id")["atok"].map(lambda ts: max((art_songs[t] for t in ts), default=1))

        wk = [w for w in sp_streams.columns if w < T] if len(sp_streams) else []
        sp_cum = sp_streams[wk].sum(axis=1).reindex(ids, fill_value=0) if wk else pd.Series(0, index=ids)
        sp_l4 = sp_streams[wk[-4:]].sum(axis=1).reindex(ids, fill_value=0) if wk else pd.Series(0, index=ids)
        sp_p4 = sp_streams[wk[-8:-4]].sum(axis=1).reindex(ids, fill_value=0) if len(wk) > 4 else 0 * sp_l4
        sp_best = sp_rank[wk].min(axis=1).reindex(ids) if wk else pd.Series(np.nan, index=ids)
        sp_weeks = (sp_streams[wk] > 0).sum(axis=1).reindex(ids, fill_value=0) if wk else pd.Series(0, index=ids)

        f = pd.DataFrame({
            "countdown_year": year, "snapshot": d, "song_id": ids,
            "title": cand["title"].values, "artist": cand["artist"].values,
            "tj_cum": cum.values, "tj_peak7": peak7.values, "tj_last28": last28.values,
            "tj_accel": ((last28 + 1) / (prev28 + 1)).values, "tj_fade": (now7 / peak7.replace(0, np.nan)).fillna(0).values,
            "tj_age": age.values, "tj_since_liftoff": since_lift.fillna(-1).values,
            "tj_artist_share": (cum / a_tot.reindex(ids).replace(0, np.nan)).fillna(0).values,
            "tj_artist_songs": a_n.reindex(ids).values, "tj_artist_plays": a_tot.reindex(ids).values,
            "sp_cum": sp_cum.values, "sp_best_rank": sp_best.fillna(250).values, "sp_weeks": sp_weeks.values,
            "sp_last4": sp_l4.values, "sp_accel": ((sp_l4 + 1) / (sp_p4 + 1)).values,
            "sp_charted": (sp_weeks > 0).astype(int).values, "is_lav": is_lav.reindex(ids).values,
        })
        # Candidacy is judged at T itself, so early snapshots never use later airplay.
        f = f[(f["tj_cum"] >= MIN_PLAYS) & (f["tj_peak7"] >= MIN_PEAK7)].reset_index(drop=True)
        f["n_candidates"] = len(f)
        for c in RAW:
            if c in ("sp_charted", "is_lav"):
                continue
            pct = f[c].rank(pct=True, method="average")
            f[f"p_{c}"] = 1 - pct + 1 / len(f) if c in LOWER_IS_BETTER else pct
        rows.append(f)
    return pd.concat(rows, ignore_index=True)
