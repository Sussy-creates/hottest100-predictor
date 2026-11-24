"""Download one Wayback capture per day of each archived chart page (raw HTML, untouched).

Saves data/raw/wayback/<name>/<YYYYMMDDhhmmss>.html.gz; already-downloaded captures are skipped.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "wayback"
UA = {"User-Agent": "hottest100-predictor research (github.com/Sussy-creates)"}
PAGES = {
    "kworb_youtube_au_daily": "kworb.net/youtube/insights/au_daily.html",
    "kworb_youtube_au_weekly": "kworb.net/youtube/insights/au.html",
    "kworb_shazam_au": "kworb.net/charts/shazam/au.html",
    "shazam_top100_au_old": "shazam.com/charts/top-100/australia",
    "shazam_au_top_100_old": "shazam.com/charts/au_top_100",
}


def get(url: str, timeout: int = 120) -> bytes | None:
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * 2 ** attempt)
        except Exception:  # noqa: BLE001
            time.sleep(5 * 2 ** attempt)
    return None


def main() -> None:
    for name, url in PAGES.items():
        q = urllib.parse.urlencode({"url": url, "output": "json", "fl": "timestamp,original",
                                    "filter": "statuscode:200", "collapse": "timestamp:8"})
        body = get(f"https://web.archive.org/cdx/search/cdx?{q}", timeout=300)
        rows = json.loads(body)[1:] if body and body.strip() else []
        out = ROOT / name
        out.mkdir(parents=True, exist_ok=True)
        new = 0
        for ts, original in rows:
            path = out / f"{ts}.html.gz"
            if path.exists():
                continue
            html = get(f"https://web.archive.org/web/{ts}id_/{original}")
            if html:
                path.write_bytes(gzip.compress(html))
                new += 1
            time.sleep(1.5)
        print(f"{name}: {len(rows)} captures listed, {new} downloaded", flush=True)


if __name__ == "__main__":
    main()
