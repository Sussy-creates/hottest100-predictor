"""Public Spotify playlists of Hottest 100 votes / predictions: daily snapshots of who lists which songs.

1. Spotify Web API search (client credentials; secrets SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET) for playlists
   named like "hottest 100 <year> votes". Dev Mode returns 10 results per page, so each query pages by offset.
2. Track lists come from the public embed page (open.spotify.com/embed/playlist/<id>, first 100 tracks): Dev Mode
   blocks the API's playlist-items endpoint for playlists we don't own.

Each run writes a dated snapshot, so a playlist's contents can be taken as of voting close (first and last seen):
  data/raw/spotify_playlists/<run date>/search.jsonl   one row per (query, playlist) hit
  data/raw/spotify_playlists/<run date>/tracks.jsonl   one row per (playlist, position)

Usage: python scripts/fetch_spotify_playlists.py [year ...]   (default: the live year)
Past years' playlists can have been edited after their countdown, so they are only a rough check, not a backtest.
"""
import base64, hashlib, hmac, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) hottest100-predictor research"}
PAGES = 10  # x 10 results per query (later pages are almost all unrelated playlists)
MAX_TRACKS = 100


def http(url, data=None, headers=None, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 10) or 10)
                print("429, Retry-After", wait, url[:90], flush=True)
                if wait > 120:  # a long rate-limit penalty: give up on this call rather than hang the run
                    return 429, body
                time.sleep(wait + 1); continue
            if e.code in (400, 401, 403, 404):
                return e.code, body
        except Exception as e:  # noqa: BLE001
            body = repr(e)[:200]
        time.sleep(3 * (i + 1))
    return None, body


class RateLimited(Exception):
    pass


def token():
    cid, sec = os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"]
    st, body = http("https://accounts.spotify.com/api/token", data=b"grant_type=client_credentials",
                    headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                             "Content-Type": "application/x-www-form-urlencoded"})
    if st != 200:
        sys.exit(f"token request failed: {st} {body}")
    return json.loads(body)["access_token"]


def owner_hash(o):
    """Playlist owners are private people and the repo is public: keep only a keyed hash (stable across runs)."""
    if not o or o.startswith("triple.j") or o == "spotify":
        return o
    return hmac.new(os.environ["SPOTIFY_CLIENT_SECRET"].encode(), o.encode(), hashlib.sha256).hexdigest()[:16]


def queries(y):
    return [f"hottest 100 {y}", f"hottest 100 {y} votes", f"my hottest 100 {y}", f"hottest 100 {y} predictions",
            f"hottest 100 of {y}", f"h100 {y}", f"triple j hottest 100 {y}", f"hottest 100 votes {y}",
            f"my h100 votes {y}", f"hottest 100 {y} my votes"]


def relevant(name, y):
    n = name.lower()
    return str(y) in n and bool(re.search(r"hottest|h100|triple ?j", n))


def search(tok, q):
    out = []
    for page in range(PAGES):
        url = "https://api.spotify.com/v1/search?" + urllib.parse.urlencode(
            dict(q=q, type="playlist", limit=10, offset=10 * page, market="AU"))
        st, body = http(url, headers={"Authorization": f"Bearer {tok}"})
        if st == 429:
            raise RateLimited(out)
        if st != 200:
            print("search", st, q, page, body[:200], flush=True); break
        res = json.loads(body).get("playlists") or {}
        raw = res.get("items") or []
        out += [p for p in raw if p]  # the API returns null for some removed playlists
        if not res.get("next") or not raw:
            break
        time.sleep(1.5)  # gentle: hammering search earns a ~20-hour 429 penalty
    return out


def embed_tracks(pid):
    st, body = http(f"https://open.spotify.com/embed/playlist/{pid}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body or "", re.S)
    if st != 200 or not m:
        return None
    ent = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    return [dict(pos=i, title=t.get("title"), artists=t.get("subtitle"), uri=t.get("uri"))
            for i, t in enumerate(ent.get("trackList") or [])]


def main(years):
    tok = token()
    out = ROOT / "data/raw/spotify_playlists" / date.today().isoformat()
    hits, seen, limited = [], {}, False
    for y in years:
        for q in queries(y):
            try:
                found = search(tok, q)
            except RateLimited as e:
                found, limited = e.args[0], True
            for p in found:
                tr = p.get("tracks") or p.get("items") or {}
                row = dict(year=y, query=q, id=p.get("id"), name=p.get("name"), description=p.get("description"),
                           owner=owner_hash((p.get("owner") or {}).get("id")), n_tracks=tr.get("total"), snapshot_id=p.get("snapshot_id"))
                hits.append(row)
                if relevant(row["name"] or "", y) and (row["n_tracks"] or 0) <= MAX_TRACKS:
                    seen.setdefault(row["id"], row)
            if limited:
                print("rate limited by Spotify: stopping the search, keeping what was found", flush=True)
                break
        if limited:
            break
        print(y, f"{sum(h['year'] == y for h in hits)} search hits, {sum(r['year'] == y for r in seen.values())} relevant playlists", flush=True)
    if not hits:  # don't overwrite an earlier snapshot from today with an empty one
        print("no search hits: nothing written", flush=True)
        return
    out.mkdir(parents=True, exist_ok=True)
    if (out / "search.jsonl").exists():
        out = out.with_name(out.name + "_" + time.strftime("%H%M")); out.mkdir()
    with open(out / "search.jsonl", "w") as fh:
        for h in hits:
            fh.write(json.dumps(h, ensure_ascii=False) + "\n")
    n = bad = 0
    with open(out / "tracks.jsonl", "w") as fh:
        for pid, r in seen.items():
            ts = embed_tracks(pid)
            if ts is None:
                bad += 1; continue
            for t in ts:
                fh.write(json.dumps({"playlist_id": pid, "year": r["year"], **t}, ensure_ascii=False) + "\n"); n += 1
            time.sleep(0.5)
    print(f"{len(seen)} playlists, {n} track rows, {bad} embed pages failed", flush=True)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [2026])
