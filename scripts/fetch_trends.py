"""Google Trends (AU, daily) for one countdown year's target artists, scaled against a shared anchor.

Each request holds 4 artists plus the anchor, so every value can be divided by the anchor's value in the
same request and compared across batches and years. Artists are queried as their Google Knowledge Graph
topic (a music-type entity from Trends' own suggestions) when one is found, else as a plain search term.

Writes data/raw/trends/<year>.csv (long: date, artist, keyword, kw_type, value, anchor, batch).
Artists already in the file are skipped, so a rerun resumes.

Usage: python scripts/fetch_trends.py 2019
"""
import csv, re, sys, time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_NAME = "Hilltop Hoods"  # Australian act with steady, moderate search volume (tested in the probe)
MUSIC = re.compile(r"band|music|singer|rapper|artist|group|dj|producer|duo|songwriter|composer|rock|hip hop|"
                   r"vocalist|performer|ensemble|trio|orchestra|entertainer", re.I)
PAUSE, BACKOFF = 12, 60


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^the\s+", "", s.lower()))


def topic(t: TrendReq, name: str):
    for attempt in range(3):
        try:
            for s in t.suggestions(keyword=name):
                if MUSIC.search(s.get("type", "")) and norm(s.get("title", "")) == norm(name):
                    return s["mid"], "topic"
            return name, "term"
        except Exception as e:  # noqa: BLE001
            print("suggest error", name, repr(e)[:100], flush=True)
            time.sleep(BACKOFF * (attempt + 1))
    return name, "term"


def main(year: int) -> None:
    tg = pd.read_csv(ROOT / "data/derived/trends_targets.csv")
    tg = tg[tg.countdown_year == year]
    tf = f"{tg.window_start.iloc[0]} {tg.window_end.iloc[0]}"
    out = ROOT / "data/raw/trends" / f"{year}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set(pd.read_csv(out).artist) if out.exists() else set()
    todo = [a for a in tg.artist if a not in done]
    print(year, tf, len(todo), "to fetch,", len(done), "already done", flush=True)
    t = TrendReq(hl="en-AU", tz=-600, retries=3, backoff_factor=10)
    anchor_kw, _ = topic(t, ANCHOR_NAME)
    new = not out.exists()
    fh = open(out, "a", newline="")
    w = csv.writer(fh)
    if new:
        w.writerow(["date", "artist", "keyword", "kw_type", "value", "anchor", "batch"])
    for i in range(0, len(todo), 4):
        names = todo[i:i + 4]
        kws = []
        for n in names:
            kw, kt = topic(t, n); time.sleep(2)
            kws.append((n, kw, kt))
        uniq = list(dict.fromkeys(k for _, k, _ in kws if k != anchor_kw))
        for attempt in range(4):
            try:
                t.build_payload(uniq + [anchor_kw], geo="AU", timeframe=tf)
                df = t.interest_over_time()
                break
            except Exception as e:  # noqa: BLE001
                print(year, names, "error", repr(e)[:120], flush=True)
                df = None; time.sleep(BACKOFF * (attempt + 1))
        if df is None or df.empty:
            print(year, names, "no data", flush=True)
            for n, kw, kt in kws:  # record the artist so a rerun doesn't loop on it; value blank
                w.writerow(["", n, kw, kt, "", "", i // 4])
        else:
            for n, kw, kt in kws:
                col = df[anchor_kw] if kw == anchor_kw else df[kw]
                for d, v, a in zip(df.index, col, df[anchor_kw]):
                    w.writerow([d.date().isoformat(), n, kw, kt, int(v), int(a), i // 4])
        fh.flush()
        print(year, f"batch {i // 4 + 1}/{(len(todo) + 3) // 4}", [k[2] for k in kws], flush=True)
        time.sleep(PAUSE)
    fh.close()


if __name__ == "__main__":
    main(int(sys.argv[1]))
