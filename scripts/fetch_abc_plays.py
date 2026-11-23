"""Backfill every triple j play from the ABC Radio API for one calendar year.

Writes data/raw/abc_plays/<year>/<year>-<month>.jsonl.gz, one slimmed play per line.
Months already on disk are skipped unless they are the current month (still filling).

Usage: python scripts/fetch_abc_plays.py 2019 [--out data/raw/abc_plays]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://music.abcradio.net.au/api/v1/plays/search.json"
UA = {"User-Agent": "hottest100-predictor research backfill (github.com/Sussy-creates)"}
EARLIEST = datetime(2014, 12, 1, tzinfo=timezone.utc)  # first month the 2015 countdown needs
WINDOW = timedelta(hours=6)  # ~90 plays; offset paging covers anything over the 100 cap
LIMIT = 100
PAUSE = 0.4  # seconds between calls


def call(params: dict, tries: int = 6) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}/{tries} in {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def slim(item: dict) -> dict:
    rec = item.get("recording") or {}
    rel = (rec.get("releases") or [{}])[0] or {}
    summ = item.get("summary") or {}
    return {
        "play_id": item.get("arid"),
        "played_time": item.get("played_time"),
        "recording_id": rec.get("arid"),
        "title": rec.get("title"),
        "summary_artist": summ.get("artist"),
        "summary_title": summ.get("title"),
        "duration": rec.get("duration"),
        "artists": [
            {"id": a.get("arid"), "name": a.get("name"), "type": a.get("type"),
             "is_australian": a.get("is_australian")}
            for a in rec.get("artists") or []
        ],
        "release_id": rel.get("arid"),
        "release_title": rel.get("title"),
        "release_format": rel.get("format"),
    }


def fetch_window(start: datetime, end: datetime) -> list[dict]:
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    out, offset = [], 0
    while True:
        data = call({"station": "triplej", "from": start.strftime(fmt), "to": end.strftime(fmt),
                     "limit": LIMIT, "offset": offset})
        items = data.get("items") or []
        out.extend(items)
        time.sleep(PAUSE)
        total = data.get("total") or 0
        offset += len(items)
        if not items or offset >= total:
            return out


def fetch_month(month_start: datetime, now: datetime) -> list[dict]:
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    end = min(month_end, now)
    seen, rows, t = set(), [], month_start
    while t < end:
        for item in fetch_window(t, min(t + WINDOW, end)):
            pid = item.get("arid")
            if pid and pid not in seen:  # windows share boundaries; dedupe on play id
                seen.add(pid)
                rows.append(slim(item))
        t += WINDOW
    rows.sort(key=lambda r: r["played_time"] or "")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("--out", default="data/raw/abc_plays")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    out_dir = Path(args.out) / str(args.year)
    out_dir.mkdir(parents=True, exist_ok=True)

    for m in range(1, 13):
        ms = datetime(args.year, m, 1, tzinfo=timezone.utc)
        if ms < EARLIEST or ms > now:
            continue
        path = out_dir / f"{args.year}-{m:02d}.jsonl.gz"
        current = ms.year == now.year and ms.month == now.month
        if path.exists() and not current:
            print(f"{path.name}: already have it, skipping")
            continue
        t0 = time.time()
        rows = fetch_month(ms, now)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{path.name}: {len(rows)} plays in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
