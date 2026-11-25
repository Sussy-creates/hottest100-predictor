"""Fetch the Wikipedia page for each Hottest 100 countdown (rendered HTML + wikitext).

Raw API responses go to data/raw/wikipedia/<year>.json. Parsing happens separately
(scripts/parse_results.py) so it can be iterated on without re-fetching.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "wikipedia"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "hottest100-predictor/0.1 (research; github.com/Sussy-creates)"}
API = "https://en.wikipedia.org/w/api.php"
TITLES = ["Triple J's Hottest 100 of {y}", "Triple J Hottest 100, {y}"]


def parse(title: str) -> dict | None:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text|wikitext|revid",
                                "redirects": 1, "format": "json", "formatversion": 2})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers=UA), timeout=60) as r:
                data = json.loads(r.read())
            return None if "error" in data else data["parse"]
        except urllib.error.HTTPError as e:
            print(f"  {title}: HTTP {e.code}, retry {attempt + 1}")
            time.sleep(5 * 2 ** attempt)
    return None


def main() -> None:
    for y in range(2005, 2026):
        if (OUT / f"{y}.json").exists():
            continue
        page = None
        for t in TITLES:
            page = parse(t.format(y=y))
            time.sleep(1)
            if page:
                break
        if not page:
            print(f"{y}: NOT FOUND")
            continue
        (OUT / f"{y}.json").write_text(json.dumps(page))
        print(f"{y}: {page['title']} rev {page.get('revid')} ({len(page['text'])} chars)")


if __name__ == "__main__":
    main()
