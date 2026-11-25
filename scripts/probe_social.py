"""Feasibility probe for vote-like public signals. Writes data/probe/social.json.

1. Reddit via the Arctic Shift archive: r/triplej posts and comments in each year's voting window.
2. Spotify user playlists: does the public embed page carry the track list (and any dates)?
3. Playlist discovery: how many "hottest 100 <year>" playlist pages a web search returns.
4. Bluesky public search: posts about Hottest 100 votes in the 2025 voting window.
"""
import csv, json, re, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) hottest100-predictor research probe"}
out = {}


def get(url, tries=2):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:200]; time.sleep(3)
    return None, err


cal = {int(r["countdown_year"]): r for r in csv.DictReader(open(ROOT / "config/countdowns.csv"))}

# 1. Arctic Shift
AS = "https://arctic-shift.photon-reddit.com/api"
reddit = {}
for y in range(2015, 2026):
    lo, hi = cal[y]["voting_open"], cal[y]["voting_close_aedt"][:10]
    st, body = get(f"{AS}/posts/search?subreddit=triplej&after={lo}&before={hi}&limit=100&sort=desc&sort_type=num_comments"
                   f"&fields=id,title,num_comments,created_utc")
    try:
        posts = json.loads(body).get("data", [])
    except Exception:  # noqa: BLE001
        reddit[y] = {"status": st, "error": body[:300]}; continue
    votey = [p for p in posts if re.search(r"vot|hottest|countdown|predict", p.get("title", ""), re.I)]
    st2, b2 = get(f"{AS}/comments/search?subreddit=triplej&after={lo}&before={hi}&limit=100&body=voted&fields=id,body,created_utc,link_id")
    try:
        com = json.loads(b2).get("data", [])
    except Exception:  # noqa: BLE001
        com = []
    reddit[y] = {"status": st, "posts_returned": len(posts),
                 "vote_posts": sorted([(p["num_comments"], p["title"], p["id"]) for p in votey], reverse=True)[:8],
                 "comments_with_voted": len(com), "sample_comment": (com[0]["body"][:400] if com else "")}
    time.sleep(1)
out["reddit_arctic_shift"] = reddit

# 2. Spotify embed page for a known public prediction playlist
pl = "0SSD8f8WrsOyO5HKQsKJrp"  # "Hottest 100 2025 Predictions" (public)
st, body = get(f"https://open.spotify.com/embed/playlist/{pl}")
info = {"status": st, "len": len(body or "")}
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body or "", re.S)
if m:
    try:
        nd = json.loads(m.group(1))
        ent = nd["props"]["pageProps"]["state"]["data"]["entity"]
        tl = ent.get("trackList", [])
        info.update(name=ent.get("name"), n_tracks=len(tl), first=[(t.get("title"), t.get("subtitle")) for t in tl[:5]],
                    entity_keys=sorted(ent.keys()), track_keys=sorted(tl[0].keys()) if tl else [])
    except Exception as e:  # noqa: BLE001
        info["parse_error"] = repr(e)[:200]
else:
    info["snippet"] = (body or "")[:500]
out["spotify_embed"] = info

# 3. Playlist discovery via DuckDuckGo HTML results
disc = {}
for y in (2018, 2020, 2022, 2024, 2025):
    q = f'site:open.spotify.com/playlist "hottest 100" {y}'
    st, body = get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q))
    ids = sorted(set(re.findall(r"open\.spotify\.com(?:%2F|/)playlist(?:%2F|/)([A-Za-z0-9]{22})", body or "")))
    disc[y] = {"status": st, "playlist_ids_on_first_page": len(ids), "ids": ids[:10]}
    time.sleep(4)
out["playlist_discovery_ddg"] = disc

# 4. Bluesky public search
bs = {}
for q in ('"hottest 100" votes', '"hottest 100" voted'):
    url = ("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?" +
           urllib.parse.urlencode({"q": q, "since": "2025-12-08T00:00:00Z", "until": "2026-01-16T00:00:00Z", "limit": 100}))
    st, body = get(url)
    try:
        posts = json.loads(body).get("posts", [])
        bs[q] = {"status": st, "n": len(posts), "cursor": bool(json.loads(body).get("cursor")),
                 "sample": [p["record"].get("text", "")[:200] for p in posts[:3]]}
    except Exception:  # noqa: BLE001
        bs[q] = {"status": st, "error": (body or "")[:300]}
out["bluesky"] = bs

(ROOT / "data/probe").mkdir(parents=True, exist_ok=True)
(ROOT / "data/probe/social.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, indent=1, ensure_ascii=False)[:6000])
