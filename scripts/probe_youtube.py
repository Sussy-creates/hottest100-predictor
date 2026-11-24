"""How far back do YouTube's weekly Australian charts go, and in what shape?

1. Read the public charts page config (API key, client version) from charts.youtube.com.
2. Ask the charts backend for AU weekly Top Songs / Top Music Videos at dates from 2016 to now.
3. Count Wayback captures of kworb's YouTube AU page as a fallback.
Writes data/probe/youtube_probe.json (+ one raw sample response).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-AU,en;q=0.9"}
DATES = ["2016-06-02", "2018-01-04", "2019-06-06", "2020-01-02", "2021-01-07", "2022-01-06",
         "2023-01-05", "2024-01-04", "2025-01-09", "2026-11-19"]


def http(url, data=None, headers=None, timeout=60):
    h = dict(UA, **(headers or {}))
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def find_config(html: str) -> dict:
    out = {}
    for k in ("INNERTUBE_API_KEY", "INNERTUBE_CLIENT_VERSION", "INNERTUBE_CLIENT_NAME", "INNERTUBE_CONTEXT_CLIENT_NAME"):
        m = re.search(rf'"{k}"\s*:\s*"?([^",]+)"?', html)
        if m:
            out[k] = m.group(1)
    return out


def walk(obj, key):
    """Yield every value stored under `key` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, key)


def chart(cfg, chart_type, end_date):
    key = cfg.get("INNERTUBE_API_KEY", "")
    url = f"https://charts.youtube.com/youtubei/v1/browse?alt=json&key={key}"
    body = {
        "context": {"client": {"clientName": "WEB_MUSIC_ANALYTICS",
                               "clientVersion": cfg.get("INNERTUBE_CLIENT_VERSION", "2.0"),
                               "hl": "en", "gl": "AU", "theme": "MUSIC"},
                    "capabilities": {}, "request": {"internalExperimentFlags": []}},
        "browseId": "FEmusic_analytics_charts_home",
        "query": (f"perspective=CHART_DETAILS&chart_params_country_code=au&chart_params_chart_type={chart_type}"
                  f"&chart_params_period_type=WEEKLY&chart_params_end_date={end_date}"),
    }
    status, text = http(url, json.dumps(body).encode(), {"Content-Type": "application/json",
                                                         "Origin": "https://charts.youtube.com",
                                                         "Referer": "https://charts.youtube.com/"})
    res = {"status": status, "bytes": len(text)}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        res["body_head"] = text[:300]
        return res, None
    entries = list(walk(data, "trackViews")) or list(walk(data, "videoViews"))
    first = entries[0][0] if entries and isinstance(entries[0], list) and entries[0] else None
    res["n_entries"] = len(entries[0]) if entries and isinstance(entries[0], list) else 0
    res["first_entry"] = first
    res["end_dates_seen"] = sorted({v for v in walk(data, "endDate")})[:5]
    if not res["n_entries"]:
        res["top_keys"] = list(data.keys())[:10]
        res["error"] = data.get("error")
    return res, data


def main():
    report = {}
    status, html = http("https://charts.youtube.com/charts/TopSongs/au/weekly")
    cfg = find_config(html)
    report["page"] = {"status": status, "bytes": len(html), "config": cfg}
    sample_saved = False
    for ct in ("TRACKS", "VIDEOS"):
        report[ct] = {}
        for d in DATES:
            res, data = chart(cfg, ct, d)
            report[ct][d] = res
            if data is not None and res.get("n_entries") and not sample_saved:
                (OUT / "youtube_chart_sample.json").write_text(json.dumps(data)[:2_000_000])
                sample_saved = True
            time.sleep(2)

    q = urllib.parse.urlencode({"url": "kworb.net/youtube/insights/au_daily.html", "output": "json",
                                "fl": "timestamp", "filter": "statuscode:200", "collapse": "timestamp:6"})
    s, body = http(f"https://web.archive.org/cdx/search/cdx?{q}", timeout=180)
    try:
        months = [r[0][:6] for r in json.loads(body)[1:]]
    except Exception:  # noqa: BLE001
        months = []
    report["wayback_kworb_youtube_au_months"] = months

    (OUT / "youtube_probe.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
