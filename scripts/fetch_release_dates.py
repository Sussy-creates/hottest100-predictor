"""Release dates from the iTunes Search API (Australian store, no key) for one year's target songs.

For each song, searches "<lead artist> <title>" and keeps results whose artist shares a word with ours
and whose title key matches; records the earliest releaseDate among them (singles usually come out before
the album the track also sits on). Writes data/raw/release_dates/<year>.csv; reruns skip songs done.

Usage: python scripts/fetch_release_dates.py 2019
"""
import csv, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
API = "https://itunes.apple.com/search"
PAUSE = 3.2  # Apple allows roughly 20 calls a minute
SPLIT = re.compile(r"\s+(?:featuring|feat\.?|ft\.?|with|x|vs\.?|&|and)\s+|,\s*|\s+/\s+", re.I)


def key(s: str) -> str:
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", str(s).lower())  # drop (feat. ...), [Like A Version] etc.
    s = re.split(r"\s+-\s+", s)[0]
    return re.sub(r"[^a-z0-9]", "", s)


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", str(s).lower()) if w not in {"the", "and", "feat", "ft", "x"}}


def search(term: str):
    url = f"{API}?{urllib.parse.urlencode({'term': term, 'country': 'au', 'media': 'music', 'entity': 'song', 'limit': 50})}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hottest100-predictor"}), timeout=30) as r:
                return json.loads(r.read()).get("results", [])
        except Exception as e:  # noqa: BLE001
            print("retry", term, repr(e)[:80], flush=True); time.sleep(20 * (attempt + 1))
    return None


def main(year: int) -> None:
    tg = pd.read_csv(ROOT / "data/derived/release_targets.csv")
    tg = tg[tg.countdown_year == year]
    out = ROOT / "data/raw/release_dates" / f"{year}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set(pd.read_csv(out).song_id) if out.exists() else set()
    new = not out.exists()
    fh = open(out, "a", newline=""); w = csv.writer(fh)
    if new:
        w.writerow(["countdown_year", "song_id", "title", "artist", "release_date", "n_matches", "matched_title", "matched_artist", "collection"])
    todo = tg[~tg.song_id.isin(done)]
    print(year, len(todo), "to fetch", flush=True)
    for n, r in enumerate(todo.itertuples(), 1):
        lead = SPLIT.split(str(r.artist))[0]
        title = re.sub(r"[\(\[].*?[\)\]]", "", str(r.title))
        res = search(f"{lead} {title}")
        if res is None:
            continue  # leave for a rerun
        k, aw = key(r.title), words(r.artist)
        hits = [x for x in res if key(x.get("trackName", "")) == k and words(x.get("artistName", "")) & aw and x.get("releaseDate")]
        best = min(hits, key=lambda x: x["releaseDate"]) if hits else {}
        w.writerow([year, r.song_id, r.title, r.artist, best.get("releaseDate", "")[:10], len(hits),
                    best.get("trackName", ""), best.get("artistName", ""), best.get("collectionName", "")])
        fh.flush()
        if n % 50 == 0:
            print(year, n, "/", len(todo), flush=True)
        time.sleep(PAUSE)
    fh.close()


if __name__ == "__main__":
    main(int(sys.argv[1]))
