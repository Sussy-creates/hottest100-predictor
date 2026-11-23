"""(1) Re-query sparse triple j airplay days hour by hour to confirm the gaps are in the ABC log.
(2) Save every Wayback capture timestamp for the Shazam AU chart pages.

Writes data/probe/abc_gap_recheck.json and data/probe/wayback_shazam_captures.csv.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "hottest100-predictor research probe (github.com/Sussy-creates)"}

# Longest gap per sparse day, UTC, padded by an hour either side.
GAPS = [
    ("2014-12-06T15:00", "2014-12-07T01:00"), ("2016-01-22T09:00", "2016-01-23T00:00"),
    ("2016-05-28T07:00", "2016-05-30T00:00"), ("2016-06-18T09:00", "2016-06-20T01:00"),
    ("2016-09-24T09:00", "2016-09-24T21:00"), ("2017-07-21T13:00", "2017-07-22T01:00"),
    ("2018-07-21T12:00", "2018-07-21T20:00"), ("2018-08-11T10:00", "2018-08-11T21:00"),
    ("2018-09-29T07:00", "2018-09-29T16:00"), ("2019-01-05T05:00", "2019-01-06T00:00"),
    ("2020-10-18T09:00", "2020-10-18T20:00"), ("2021-12-18T03:00", "2021-12-20T00:00"),
    ("2021-12-31T18:00", "2022-01-01T07:00"), ("2022-11-10T11:00", "2022-11-11T00:00"),
    ("2024-07-19T03:00", "2024-07-20T01:00"), ("2024-12-31T11:00", "2025-01-01T11:00"),
]

WAYBACK = {
    "kworb_shazam_au": "kworb.net/charts/shazam/au.html",
    "shazam_top100_au_old": "shazam.com/charts/top-100/australia",
    "shazam_top200_au": "shazam.com/charts/top-200/australia",
}


def get_json(url: str, timeout: int = 60):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                body = r.read()
                return json.loads(body) if body.strip() else []
        except Exception as e:  # noqa: BLE001
            print(f"retry {attempt + 1}: {e}")
            time.sleep(3 * 2 ** attempt)
    return None


def recheck() -> list[dict]:
    api = "https://music.abcradio.net.au/api/v1/plays/search.json"
    out = []
    for s, e in GAPS:
        t, end = datetime.fromisoformat(s).replace(tzinfo=timezone.utc), datetime.fromisoformat(e).replace(tzinfo=timezone.utc)
        hours = []
        while t < end:
            q = urllib.parse.urlencode({"station": "triplej", "from": t.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                        "to": (t + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "limit": 100})
            d = get_json(f"{api}?{q}") or {}
            hours.append({"hour_utc": t.strftime("%Y-%m-%dT%H"), "total": d.get("total")})
            time.sleep(0.4)
            t += timedelta(hours=1)
        out.append({"window": [s, e], "hours": hours,
                    "empty_hours": sum(1 for h in hours if not h["total"])})
    return out


def captures() -> list[tuple[str, str]]:
    rows = []
    for name, url in WAYBACK.items():
        q = urllib.parse.urlencode({"url": url, "output": "json", "fl": "timestamp,statuscode",
                                    "filter": "statuscode:200"})
        data = get_json(f"https://web.archive.org/cdx/search/cdx?{q}", timeout=180) or []
        rows += [(name, r[0]) for r in data[1:]]
        time.sleep(5)
    return rows


def main() -> None:
    (OUT / "abc_gap_recheck.json").write_text(json.dumps(recheck(), indent=1))
    with open(OUT / "wayback_shazam_captures.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "timestamp"])
        w.writerows(captures())
    print("done")


if __name__ == "__main__":
    main()
