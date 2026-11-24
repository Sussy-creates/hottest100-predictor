"""Daily snapshot of live chart pages, so this year's prediction never depends on Wayback.

Saves gzipped pages under data/raw/daily/<source>/<YYYY-MM-DD>.html.gz (UTC date).
Re-running on the same day overwrites that day's file, so extra runs are harmless.
"""
from __future__ import annotations

import gzip
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "daily"
UA = {"User-Agent": "hottest100-predictor daily collector (github.com/Sussy-creates)"}

PAGES = {
    "kworb_shazam_au": "https://kworb.net/charts/shazam/au.html",
    "kworb_spotify_au_daily": "https://kworb.net/spotify/country/au_daily.html",
    "kworb_apple_au": "https://kworb.net/charts/apple_s/au.html",
    "shazam_top200_au_csv": "https://www.shazam.com/services/charts/csv/top-200/australia",
}


def main() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for name, url in PAGES.items():
        out = ROOT / name / f"{day}.html.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                body = r.read()
            with gzip.open(out, "wb") as f:
                f.write(body)
            print(f"{name}: {len(body)} bytes")
        except Exception as e:  # noqa: BLE001
            print(f"{name}: FAILED {e}")
        time.sleep(2)


if __name__ == "__main__":
    main()
