"""Probe: can we build a panel of triple j listeners on Spotify (Dev Mode API + public pages)?
Writes only aggregate, de-identified results to data/probe/spotify_panel.json (no user ids or names).

1. For owners of 2025 'Hottest 100 votes' playlists: does /users/{id}/playlists list their other public playlists?
   What kinds of playlists are they (names bucketed by keyword), and do embed pages give their tracks?
2. triple j's own playlists (owner triple.j.abc): which exist, follower counts, track lists via embed.
3. Artist endpoints: followers / popularity / genres / related artists still returned?
4. Public artist page: monthly listeners and top cities in the HTML?
"""
import base64, collections, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_spotify_playlists import embed_tracks, http, token

ROOT = Path(__file__).resolve().parents[1]
tok = token(); H = {"Authorization": f"Bearer {tok}"}
api = lambda path: http("https://api.spotify.com/v1/" + path, headers=H)
out = {}

snap = sorted((ROOT / "data/raw/spotify_playlists").glob("*"))[0]
s = [json.loads(l) for l in open(snap / "search.jsonl")]
owners = list(dict.fromkeys(r["owner"] for r in s if r["year"] == 2025 and r["owner"] and re.search(r"vote", r["name"] or "", re.I)))[:12]
kinds = collections.Counter(); per_owner = []; statuses = collections.Counter(); embed_ok = 0; tried = 0
KW = {"hottest100": r"hottest|h100", "triplej": r"triple ?j|hitlist|like a version|unearthed", "year_faves": r"20\d\d|best of|faves|favourites|wrapped|top songs",
      "mood/genre": r"chill|indie|rock|rap|hip|house|dnb|drum|punk|vibes|party|gym|run|study|sleep"}
for o in owners:
    st, body = api(f"users/{urllib.parse.quote(o)}/playlists?limit=50")
    statuses[st] += 1
    if st != 200:
        continue
    items = [p for p in json.loads(body).get("items") or [] if p]
    per_owner.append(len(items))
    for p in items:
        n = (p.get("name") or "").lower()
        hit = [k for k, rx in KW.items() if re.search(rx, n)] or ["other"]
        kinds.update(hit)
    for p in items[:2]:
        tried += 1; embed_ok += embed_tracks(p["id"]) is not None; time.sleep(0.5)
    time.sleep(0.5)
out["user_playlists"] = dict(owners_tried=len(owners), status=dict(statuses), public_playlists_per_owner=per_owner,
                             playlist_name_kinds=dict(kinds), embed_ok=f"{embed_ok}/{tried}")

st, body = api("users/triple.j.abc/playlists?limit=50")
tj = []
if st == 200:
    for p in json.loads(body).get("items") or []:
        if not p: continue
        st2, b2 = api(f"playlists/{p['id']}?fields=name,followers.total,tracks.total,items.total")
        meta = json.loads(b2) if st2 == 200 else {"status": st2}
        tj.append(dict(name=p.get("name"), followers=(meta.get("followers") or {}).get("total"), status=st2)); time.sleep(0.3)
out["triplej_playlists"] = {"status": st, "playlists": tj}

st, body = api("search?" + urllib.parse.urlencode(dict(q="Ninajirachi", type="artist", limit=1, market="AU")))
art = (json.loads(body).get("artists") or {}).get("items", [{}])[0] if st == 200 else {}
aid = art.get("id")
out["artist_search_fields"] = sorted(art.keys()) if art else st
for path in (f"artists/{aid}", f"artists/{aid}/related-artists", f"artists/{aid}/top-tracks?market=AU"):
    st, body = api(path)
    try:
        j = json.loads(body); out[path.split("/")[-1].split("?")[0] or "artist"] = {"status": st, "keys": sorted(j.keys())[:15],
            "followers": (j.get("followers") or {}).get("total") if isinstance(j, dict) else None, "popularity": j.get("popularity")}
    except Exception:  # noqa: BLE001
        out[path] = {"status": st, "body": body[:200]}
st, html = http(f"https://open.spotify.com/artist/{aid}")
out["artist_page"] = {"status": st, "len": len(html or ""), "monthly_listeners": re.findall(r"([\d,\.]+[KM]?)\s*monthly listeners", html or "")[:3],
                      "mentions_sydney": "Sydney" in (html or ""), "mentions_melbourne": "Melbourne" in (html or "")}
(ROOT / "data/probe").mkdir(exist_ok=True)
(ROOT / "data/probe/spotify_panel.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, indent=1, ensure_ascii=False))
