"""Probe candidate new sources: ABC Unearthed / Double J airplay, Wikipedia pageviews, archived ARIA and
Apple Music charts, Google Trends. Writes data/probe/sources.json."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "hottest100-predictor research probe (github.com/Sussy-creates)"}
res: dict = {}


def get(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # noqa: BLE001
        return str(e), b""


# 1. ABC plays for other stations
abc = {}
for station in ["unearthed", "doublej", "triplejunearthed"]:
    for day in ["2015-06-01", "2017-10-02", "2020-10-01", "2024-10-01"]:
        q = urllib.parse.urlencode({"station": station, "from": f"{day}T00:00:00Z", "to": f"{day}T23:59:59Z",
                                    "limit": 100, "offset": 0})
        st, body = get(f"https://music.abcradio.net.au/api/v1/plays/search.json?{q}")
        try:
            d = json.loads(body); n = d.get("total"); items = d.get("items", [])
            sample = [(i.get("recording", {}) or {}).get("title") for i in items[:3]]
        except Exception:  # noqa: BLE001
            n, sample = None, []
        abc[f"{station} {day}"] = {"status": st, "total": n, "sample": sample}
        time.sleep(1)
res["abc_other_stations"] = abc

# 2. Wikipedia pageviews (per article, daily, from Jul 2015)
pv = {}
for art in ["Gang_of_Youths", "Spacey_Jane", "Playlunch", "Ball_Park_Music", "Paint_the_Town_Red_(Doja_Cat_song)"]:
    st, body = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
                   f"{art}/daily/20240901/20250120")
    try:
        items = json.loads(body)["items"]; pv[art] = {"status": st, "days": len(items), "views": sum(i["views"] for i in items)}
    except Exception:  # noqa: BLE001
        pv[art] = {"status": st}
    time.sleep(0.5)
res["wikipedia_pageviews"] = pv

# 3. Wayback coverage of chart pages
cdx = {}
for name, url in {
    "aria_aus_artist_singles": "ariacharts.com.au/charts/australian-artist-singles-chart",
    "aria_singles": "ariacharts.com.au/charts/singles-chart",
    "aria_aus_artist_singles_old": "ariacharts.com.au/charts/australian-artist-singles",
    "kworb_apple_au": "kworb.net/charts/apple_s/au.html",
    "kworb_itunes_au": "kworb.net/charts/itunes/au.html",
    "triplej_hitlist": "abc.net.au/triplej/hitlist",
    "unearthed_charts": "triplejunearthed.com/charts",
}.items():
    q = urllib.parse.urlencode({"url": url, "output": "json", "fl": "timestamp", "filter": "statuscode:200",
                                "collapse": "timestamp:8"})
    st, body = get(f"https://web.archive.org/cdx/search/cdx?{q}", timeout=180)
    try:
        rows = json.loads(body)[1:] if body.strip() else []
        cdx[name] = {"status": st, "days": len(rows), "by_year": dict(sorted(Counter(r[0][:4] for r in rows).items()))}
    except Exception:  # noqa: BLE001
        cdx[name] = {"status": st}
    time.sleep(2)
res["wayback"] = cdx

# 4. Google Trends
try:
    from pytrends.request import TrendReq
    t = TrendReq(hl="en-AU", tz=-600, retries=2, backoff_factor=2)
    t.build_payload(["Gang of Youths", "Ocean Alley"], geo="AU", timeframe="2017-09-01 2018-01-22")
    df = t.interest_over_time()
    res["google_trends"] = {"ok": True, "rows": len(df), "cols": list(map(str, df.columns)), "head": df.head(3).astype(str).to_dict()}
except Exception as e:  # noqa: BLE001
    res["google_trends"] = {"ok": False, "error": repr(e)[:300]}

(OUT / "sources.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
