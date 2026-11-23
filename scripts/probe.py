"""Check every data source: reachability, history depth, schema, Wayback coverage.

Stdlib only so it runs on a bare Actions runner. Writes data/probe/.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "hottest100-predictor research probe (github.com/Sussy-creates)"}

ABC = "https://music.abcradio.net.au/api/v1/plays/search.json"
CDX = "https://web.archive.org/cdx/search/cdx"

WAYBACK_TARGETS = {
    "kworb_shazam_au": "kworb.net/charts/shazam/au.html",
    "shazam_top200_au": "shazam.com/charts/top-200/australia",
    "shazam_top100_au_old": "shazam.com/charts/top-100/australia",
    "kworb_spotify_au_daily": "kworb.net/spotify/country/au_daily.html",
}

LIVE_PAGES = {
    "kworb_spotify_au_daily": "https://kworb.net/spotify/country/au_daily.html",
    "kworb_spotify_au_totals": "https://kworb.net/spotify/country/au_daily_totals.html",
    "kworb_shazam_au": "https://kworb.net/charts/shazam/au.html",
}


def get(url: str, timeout: int = 60) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # network errors
        return -1, str(e).encode()


def abc_window(start: str, end: str, limit: int = 100) -> dict:
    params = {"station": "triplej", "limit": limit}
    if start:
        params.update({"from": start, "to": end})
    q = urllib.parse.urlencode(params)
    status, body = get(f"{ABC}?{q}")
    out = {"from": start, "to": end, "status": status}
    try:
        data = json.loads(body)
        items = data.get("items", [])
        out["n_items"] = len(items)
        out["total"] = data.get("total")
        out["top_level_keys"] = sorted(data.keys())
        out["first_item"] = items[0] if items else None
    except Exception as e:
        out["error"] = f"{e}: {body[:300]!r}"
    return out


def wayback_counts(url: str) -> dict:
    q = urllib.parse.urlencode({
        "url": url, "output": "json", "fl": "timestamp",
        "filter": "statuscode:200", "collapse": "timestamp:8",  # one per day
    })
    status, body = get(f"{CDX}?{q}", timeout=120)
    out = {"url": url, "status": status}
    try:
        rows = json.loads(body)[1:] if body.strip() else []
        days = [r[0][:8] for r in rows]
        months = Counter(d[:6] for d in days)
        years = Counter(d[:4] for d in days)
        out.update({
            "n_days_captured": len(days),
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
            "days_by_year": dict(sorted(years.items())),
            "months_with_capture_by_year": dict(sorted(Counter(m[:4] for m in months).items())),
        })
    except Exception as e:
        out["error"] = f"{e}: {body[:300]!r}"
    return out


def main() -> None:
    report: dict = {"run_at": datetime.now(timezone.utc).isoformat()}

    # ABC API: schema, rows per 3-hour window, how far back history goes.
    abc = {"latest": abc_window("", "", limit=3)}
    for label, (s, e) in {
        "2024_daytime_3h": ("2024-06-04T00:00:00Z", "2024-06-04T03:00:00Z"),
        "2024_busiest_check_6h": ("2024-06-04T00:00:00Z", "2024-06-04T06:00:00Z"),
        "2019_3h": ("2019-06-04T00:00:00Z", "2019-06-04T03:00:00Z"),
        "2015_3h": ("2015-06-02T00:00:00Z", "2015-06-02T03:00:00Z"),
        "2014_3h": ("2014-12-02T00:00:00Z", "2014-12-02T03:00:00Z"),
        "2012_3h": ("2012-06-05T00:00:00Z", "2012-06-05T03:00:00Z"),
    }.items():
        abc[label] = abc_window(s, e)
        time.sleep(1)
    report["abc_api"] = abc

    # Live kworb pages: reachable, and what date they claim to cover.
    live = {}
    for name, url in LIVE_PAGES.items():
        status, body = get(url)
        text = body.decode("utf-8", "replace")
        snippet = ""
        for marker in ("Covers charts from", "Chart -", "Top Songs"):
            i = text.find(marker)
            if i >= 0:
                snippet = text[i:i + 120]
                break
        live[name] = {"status": status, "bytes": len(body), "date_snippet": snippet}
        (OUT / f"{name}.html").write_text(text)
        time.sleep(1)
    report["live_pages"] = live

    # Wayback coverage.
    wb = {}
    for name, url in WAYBACK_TARGETS.items():
        wb[name] = wayback_counts(url)
        time.sleep(2)
    report["wayback"] = wb

    (OUT / "probe_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str)[:20000])


if __name__ == "__main__":
    main()
