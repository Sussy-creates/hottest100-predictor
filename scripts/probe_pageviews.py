"""For each target (artist, close date): resolve the artist's English Wikipedia article and sum its pageviews in the
60 days before close and the 60 days before that. Writes data/probe/pageviews.csv."""
import csv, json, time, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "hottest100-predictor research (github.com/Sussy-creates)"}

def get(url):
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 ** a)
        except Exception:  # noqa: BLE001
            time.sleep(2 ** a)
    return None

cache = {}
def resolve(name):
    if name in cache: return cache[name]
    out = None
    for cand in [f"{name} (band)", f"{name} (musician)", f"{name} (singer)", f"{name} (rapper)", name]:
        q = urllib.parse.urlencode({"action": "query", "titles": cand, "redirects": 1, "prop": "pageprops|categories",
                                    "cllimit": 50, "format": "json", "formatversion": 2})
        d = get(f"https://en.wikipedia.org/w/api.php?{q}")
        pages = (d or {}).get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"): continue
        pg = pages[0]
        if "disambiguation" in (pg.get("pageprops") or {}): continue
        cats = " ".join(c["title"].lower() for c in pg.get("categories", []))
        if cand == name and not any(w in cats for w in ("musical", "musician", "singer", "band", "rapper", "songwriter", "living people", "dj")):
            continue
        out = pg["title"]; break
    cache[name] = out
    return out

def views(title, start, end):
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    d = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{t}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}")
    return sum(i["views"] for i in (d or {}).get("items", [])) if d else 0

rows = list(csv.DictReader(open(ROOT / "data/probe/pageview_targets.csv")))
for r in rows:
    close = date.fromisoformat(r["close"])
    title = resolve(r["artist_name"])
    r["wiki_title"] = title or ""
    if title and close >= date(2015, 9, 1):
        r["views_60"] = views(title, close - timedelta(days=60), close - timedelta(days=1))
        r["views_prev60"] = views(title, close - timedelta(days=120), close - timedelta(days=61))
    else:
        r["views_60"] = r["views_prev60"] = ""
    time.sleep(0.2)
with open(ROOT / "data/probe/pageviews.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(sum(1 for r in rows if r["wiki_title"]), "of", len(rows), "resolved")
