"""Last.fm panel of Australian listeners: what they played in the 120 days before each voting close.

1. discover: candidate usernames from Last.fm profile links posted on Reddit (Arctic Shift: r/lastfm, r/triplej,
   r/australia and the capital-city subs), kept if their Last.fm profile country is Australia; then grown through
   user.getFriends (two hops, Australians only). The panel (usernames) is kept in the Actions cache only, never
   committed, because the repo is public.
2. charts: for each countdown year, each panel member registered before the window, user.getWeeklyTrackChart over
   [close - 120 days, close). Only per-song totals are committed:
   data/raw/lastfm/<year>.csv = countdown_year, artist, track, listeners, plays, panel_active
   (live year: data/raw/lastfm/<year>_<run date>.csv, window ending today).

Usage: python scripts/fetch_lastfm.py [year ...]   (default 2015-2026). Needs LASTFM_API_KEY.
"""
import csv, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = os.environ["LASTFM_API_KEY"]
CACHE = ROOT / "data/cache/lastfm_panel.json"   # gitignored; persisted with actions/cache
UA = {"User-Agent": "hottest100-predictor research (github.com/Sussy-creates/hottest100-predictor)"}
AS = "https://arctic-shift.photon-reddit.com/api"
SUBS = ("lastfm", "triplej", "australia", "AustralianMusic", "melbourne", "sydney", "brisbane", "perth", "Adelaide",
        "canberra", "hobart", "indieheads", "Music")
WINDOW = 120
MAX_PANEL = 4000
last_call = [0.0]


def lfm(method, **kw):
    url = "https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode(dict(method=method, api_key=KEY, format="json", **kw))
    for i in range(4):
        wait = 0.22 - (time.time() - last_call[0])  # stay under ~5 requests a second
        if wait > 0:
            time.sleep(wait)
        last_call[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read()).get("error")
            except Exception:  # noqa: BLE001
                err = None
            if err == 29:  # rate limit
                time.sleep(30); continue
            if e.code in (400, 403, 404):
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (i + 1))
    return None


def arctic(kind, **params):
    url = f"{AS}/{kind}/search?{urllib.parse.urlencode(params)}"
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read()).get("data") or []
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return []
            time.sleep(20 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(10)
    return []


LINK = re.compile(r"last\.fm/user/([A-Za-z0-9_\-]{2,15})", re.I)


def reddit_seeds():
    names = set()
    for f in (ROOT / "data/raw/reddit").glob("*.jsonl"):
        names |= set(LINK.findall(f.read_text(errors="ignore")))
    for sub in SUBS:
        for kind, field in (("comments", "body"), ("posts", "selftext")):
            before = None
            for _ in range(30):  # newest first, up to 3,000 per sub and kind
                kw = {"subreddit": sub, field: "last.fm/user", "limit": 100, "sort": "desc"}
                if before:
                    kw["before"] = before
                d = arctic(kind, **kw)
                if not d:
                    break
                for x in d:
                    names |= set(LINK.findall(str(x.get(field) or "") + " " + str(x.get("url") or "")))
                before = int(d[-1]["created_utc"])
                if len(d) < 100:
                    break
                time.sleep(1)
        print("seeds after", sub, len(names), flush=True)
    return names


def info(u):
    j = lfm("user.getinfo", user=u)
    if not j or "user" not in j:
        return None
    x = j["user"]
    return dict(country=x.get("country") or "", registered=int((x.get("registered") or {}).get("unixtime") or 0),
                playcount=int(x.get("playcount") or 0))


def discover():
    panel = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    checked = set(panel.get("_checked", []))
    users = {k: v for k, v in panel.items() if not k.startswith("_")}
    frontier = [u for u in reddit_seeds() if u.lower() not in checked]
    for hop in range(3):  # seeds, then two hops of friends
        nxt = []
        for u in frontier:
            if u.lower() in checked or len(users) >= MAX_PANEL:
                continue
            checked.add(u.lower())
            i = info(u)
            if not i or i["country"] != "Australia" or i["playcount"] < 500:
                continue
            users[u] = i
            if hop < 2:
                fr = lfm("user.getfriends", user=u, limit=200) or {}
                nxt += [f["name"] for f in (fr.get("friends") or {}).get("user") or [] if f.get("country") == "Australia"]
        print(f"hop {hop}: panel {len(users)}, checked {len(checked)}", flush=True)
        frontier = nxt
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({**users, "_checked": sorted(checked)}))
    return users


def close_utc(row):
    c = row["voting_close_aedt"]
    if not c:
        return datetime.now(timezone.utc)
    t = datetime.fromisoformat(c if "T" in c else c + "T17:00")
    return (t - timedelta(hours=11)).replace(tzinfo=timezone.utc)  # AEDT = UTC+11


def charts(users, years):
    cal = {int(r["countdown_year"]): r for r in csv.DictReader(open(ROOT / "config/countdowns.csv"))}
    out = ROOT / "data/raw/lastfm"; out.mkdir(parents=True, exist_ok=True)
    for y in years:
        hi = close_utc(cal[y]); lo = hi - timedelta(days=WINDOW)
        plays, listeners, active = defaultdict(int), defaultdict(int), 0
        for u, i in users.items():
            if not i["registered"] or i["registered"] > lo.timestamp():
                continue
            j = lfm("user.getweeklytrackchart", user=u, **{"from": int(lo.timestamp()), "to": int(hi.timestamp())})
            if active == 0:
                print("  first chart range", ((j or {}).get("weeklytrackchart") or {}).get("@attr"), flush=True)
            tr = ((j or {}).get("weeklytrackchart") or {}).get("track") or []
            if isinstance(tr, dict):
                tr = [tr]
            if not tr:
                continue
            active += 1
            for t in tr:
                k = ((t.get("artist") or {}).get("#text") or "", t.get("name") or "")
                plays[k] += int(t.get("playcount") or 0); listeners[k] += 1
        name = f"{y}.csv" if cal[y]["voting_close_aedt"] else f"{y}_{date.today().isoformat()}.csv"
        with open(out / name, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["countdown_year", "artist", "track", "listeners", "plays", "panel_active"])
            for (a, t), n in sorted(listeners.items(), key=lambda kv: -kv[1]):
                if n >= 2:  # songs only one panel member played are dropped (privacy and noise)
                    w.writerow([y, a, t, n, plays[(a, t)], active])
        print(y, f"window {lo.date()}..{hi.date()}: {active} active panel members, {sum(1 for v in listeners.values() if v >= 2)} songs", flush=True)


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] or list(range(2015, 2027))
    users = discover()
    print("panel", len(users), "| registered before 2015:", sum(1 for i in users.values() if 0 < i["registered"] < 1420070400), flush=True)
    charts(users, years)
