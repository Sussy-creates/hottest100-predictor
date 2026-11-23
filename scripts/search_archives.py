"""Broad search of web archives for any saved copy of an Australian Shazam chart.

Wayback: prefix searches under each chart path, keeping any address that looks Australian.
archive.today: timemap per known address (may be blocked; recorded either way).
Writes data/probe/archive_search_captures.csv and data/probe/archive_search_summary.json.
"""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "hottest100-predictor research probe (github.com/Sussy-creates)"}
AU = re.compile(r"australia|/au[/._?-]|/au$|country=au|countrycode=au|[-_]au[._/]", re.I)

PREFIXES = [
    "shazam.com/charts/",
    "www.shazam.com/charts/",
    "shazam.com/services/charts/",
    "www.shazam.com/services/charts/",
    "shazam.com/shazam/v3/en/AU/",
    "kworb.net/charts/shazam/",
    "kworb.net/shazam/",
]
ARCHIVE_TODAY = [
    "https://www.shazam.com/charts/top-200/australia",
    "https://www.shazam.com/charts/top-100/australia",
    "https://kworb.net/charts/shazam/au.html",
]


def fetch(url: str, timeout: int = 300) -> tuple[int, str]:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return e.code, ""
            time.sleep(5 * 2 ** attempt)
        except Exception:  # noqa: BLE001
            time.sleep(5 * 2 ** attempt)
    return -1, ""


def wayback() -> list[tuple]:
    rows = []
    for p in PREFIXES:
        q = urllib.parse.urlencode({"url": p, "matchType": "prefix", "output": "json",
                                    "fl": "original,timestamp,statuscode,mimetype",
                                    "filter": "statuscode:200", "collapse": "timestamp:8"})
        status, body = fetch(f"https://web.archive.org/cdx/search/cdx?{q}")
        try:
            data = json.loads(body)[1:] if body.strip() else []
        except json.JSONDecodeError:
            data = []
        kept = [("wayback", r[0], r[1], r[3]) for r in data if AU.search(r[0])]
        print(f"wayback {p}: status {status}, {len(data)} captures, {len(kept)} Australian")
        rows += kept
        time.sleep(5)
    return rows


def archive_today() -> list[tuple]:
    rows = []
    for u in ARCHIVE_TODAY:
        status, body = fetch(f"https://archive.ph/timemap/{u}", timeout=60)
        stamps = re.findall(r"archive\.\w+/(\d{14})/", body)
        print(f"archive.today {u}: status {status}, {len(stamps)} captures")
        rows += [("archive.today", u, s, "") for s in stamps]
        time.sleep(5)
    return rows


def main() -> None:
    rows = wayback() + archive_today()
    with open(OUT / "archive_search_captures.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["archive", "url", "timestamp", "mimetype"])
        w.writerows(rows)
    months = defaultdict(set)
    for _, url, ts, _ in rows:
        months[ts[:4]].add(ts[:6])
    summary = {"captures": len(rows), "distinct_urls": len({r[1] for r in rows}),
               "months_with_any_capture_by_year": {y: len(m) for y, m in sorted(months.items())}}
    (OUT / "archive_search_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
