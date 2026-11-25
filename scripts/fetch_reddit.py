"""r/triplej posts and comments around each voting window, from the Arctic Shift Reddit archive (free, no key).

For each countdown year: list posts from 3 weeks before voting opens to 10 days after close, keep threads whose
title looks like votes / predictions / the countdown, and download all their comments (with timestamps, so any
feature can be cut at voting close). Writes data/raw/reddit/<year>_posts.jsonl and <year>_comments.jsonl.

Usage: python scripts/fetch_reddit.py [year ...]   (default 2015-2026)
"""
import csv, json, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://arctic-shift.photon-reddit.com/api"
UA = {"User-Agent": "hottest100-predictor research (github.com/Sussy-creates/hottest100-predictor)"}
TITLE = re.compile(r"vot|hottest|predict|countdown|top ?10|top ?100|ballot|list", re.I)
SUBS = ("triplej", "australia", "AustralianMusic")


def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read()).get("data") or []
        except urllib.error.HTTPError as e:
            print("HTTP", e.code, url, e.read()[:300], flush=True)
            if e.code == 400:
                return None
            if e.code in (422, 429):  # "Timeout. Maybe slow down a bit"
                time.sleep(30 * (i + 1)); continue
        except Exception as e:  # noqa: BLE001
            print("retry", url, repr(e)[:120], flush=True)
        time.sleep(5 * (i + 1))
    return None


def posts_in(sub, lo, hi, title=None):
    out, after = [], lo
    while True:
        kw = dict(subreddit=sub, after=after, before=hi, limit=100, sort="asc")
        if title:
            kw["title"] = title
        d = get("posts/search", **kw)
        if not d:
            return out
        out += d
        last = int(d[-1]["created_utc"])
        if len(d) < 100:
            return out
        after = last + 1
        time.sleep(1)


def comments_of(link_id):
    out, seen, after = [], set(), None
    while True:
        kw = dict(link_id=link_id, limit=100, sort="asc")
        if after:
            kw["after"] = after
        d = get("comments/search", **kw)
        if not d:
            return out
        new = [c for c in d if c.get("id") not in seen]
        seen.update(c.get("id") for c in new); out += new
        if len(d) < 100 or not new:
            return out
        after = int(d[-1]["created_utc"])  # same-second comments are deduplicated by id, not skipped
        time.sleep(2)


def main(years):
    cal = {int(r["countdown_year"]): r for r in csv.DictReader(open(ROOT / "config/countdowns.csv"))}
    out = ROOT / "data/raw/reddit"; out.mkdir(parents=True, exist_ok=True)
    for y in years:
        r = cal[y]
        if r["voting_close_aedt"]:
            lo = date.fromisoformat(r["voting_open"] or r["voting_close_aedt"][:10]) - timedelta(days=21 if r["voting_open"] else 60)
            hi = date.fromisoformat(r["voting_close_aedt"][:10]) + timedelta(days=10)
        else:  # live year: from early November to today
            lo, hi = date(y, 11, 1), date.today() + timedelta(days=1)
        posts = []
        for sub in SUBS:
            ps = [p for p in posts_in(sub, lo.isoformat(), hi.isoformat(), None if sub == "triplej" else "hottest")
                  if TITLE.search(p.get("title", ""))
                  and (sub == "triplej" or re.search(r"hottest|triple ?j", p.get("title", ""), re.I))]
            posts += ps
        keep = [p for p in posts if int(p.get("num_comments") or 0) >= 15]
        with open(out / f"{y}_posts.jsonl", "w") as fh:
            for p in posts:
                fh.write(json.dumps({k: p.get(k) for k in ("id", "subreddit", "title", "selftext", "num_comments", "created_utc", "score", "author")}) + "\n")
        n = 0
        with open(out / f"{y}_comments.jsonl", "w") as fh:
            for p in keep:
                for c in comments_of(p["id"]):
                    fh.write(json.dumps({"post_id": p["id"], "id": c.get("id"), "parent_id": c.get("parent_id"),
                                         "created_utc": c.get("created_utc"), "author": c.get("author"),
                                         "body": c.get("body"), "score": c.get("score")}) + "\n")
                    n += 1
        print(y, f"{len(posts)} matching posts, {len(keep)} with 15+ comments, {n} comments", flush=True)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or list(range(2015, 2027)))
