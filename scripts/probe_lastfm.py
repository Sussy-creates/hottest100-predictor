"""Probe Last.fm API for a triple j listener panel. Writes aggregate results only to data/probe/lastfm.json."""
import json, os, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
KEY = os.environ["LASTFM_API_KEY"]
UA = {"User-Agent": "hottest100-predictor research (github.com/Sussy-creates/hottest100-predictor)"}


def call(method, **kw):
    url = "https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode(dict(method=method, api_key=KEY, format="json", **kw))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}


def page(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


out = {}
st, j = call("artist.gettopfans", artist="Spacey Jane"); out["artist.getTopFans"] = {"status": st, "keys": list(j)[:5], "err": j.get("message")}
st, j = call("track.gettopfans", artist="Spacey Jane", track="Booster Seat"); out["track.getTopFans"] = {"status": st, "keys": list(j)[:5], "err": j.get("message")}
st, html = page("https://www.last.fm/music/Spacey+Jane/+listeners")
users = list(dict.fromkeys(re.findall(r'href="/user/([^"/?#]+)"', html)))
out["listeners_page"] = {"status": st, "users_on_page1": len(users)}
st, html2 = page("https://www.last.fm/music/Spacey+Jane/+listeners?page=2")
out["listeners_page2_users"] = len(set(re.findall(r'href="/user/([^"/?#]+)"', html2)))
st, html3 = page("https://www.last.fm/robots.txt"); out["robots_txt"] = html3[:800]
countries, regs, ok = {}, [], []
for u in users[:25]:
    st, j = call("user.getinfo", user=u)
    if st != 200:
        continue
    info = j.get("user", {}); c = info.get("country") or "None"; countries[c] = countries.get(c, 0) + 1
    regs.append(int((info.get("registered") or {}).get("unixtime") or 0))
    if c == "Australia":
        ok.append(u)
    time.sleep(0.25)
out["country_counts_of_25"] = countries
out["registered_before_2016"] = sum(1 for r in regs if 0 < r < 1451606400)
st, j = call("artist.getinfo", artist="Spacey Jane", lang="en"); out["artist_listeners_total"] = (j.get("artist") or {}).get("stats")
if ok:
    u = ok[0]
    st, j = call("user.getweeklychartlist", user=u); charts = (j.get("weeklychartlist") or {}).get("chart") or []
    out["weekly_chart_list"] = {"status": st, "n_weeks": len(charts), "first": charts[0] if charts else None}
    # arbitrary range: 120 days before the 2025 voting close (2026-01-15)
    st, j = call("user.getweeklytrackchart", user=u, **{"from": 1758153600, "to": 1768453200})
    tr = (j.get("weeklytrackchart") or {}).get("track") or []
    out["arbitrary_range_chart"] = {"status": st, "n_tracks": len(tr), "attr": (j.get("weeklytrackchart") or {}).get("@attr"),
                                    "sample_keys": sorted(tr[0].keys()) if tr else [], "err": j.get("message")}
    st, j = call("user.getrecenttracks", user=u, **{"from": 1765000000, "to": 1768453200, "limit": 200})
    out["recent_tracks"] = {"status": st, "total": ((j.get("recenttracks") or {}).get("@attr") or {}).get("total")}
    st, j = call("user.getfriends", user=u, limit=50); out["friends"] = {"status": st, "n": len((j.get("friends") or {}).get("user") or [])}
(ROOT / "data/probe").mkdir(exist_ok=True)
(ROOT / "data/probe/lastfm.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
