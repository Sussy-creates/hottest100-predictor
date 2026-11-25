"""Probe Google Trends (AU) for historical song/artist search interest. Writes data/probe/trends.json."""
import json, time
from pathlib import Path
from pytrends.request import TrendReq

OUT = Path(__file__).resolve().parents[1] / "data" / "probe"; OUT.mkdir(parents=True, exist_ok=True)
res = {}
t = TrendReq(hl="en-AU", tz=-600, retries=3, backoff_factor=5)
tests = [(["Gang of Youths", "Ocean Alley", "Post Malone"], "2017-09-01 2018-01-22"),
         (["Playlunch Keith", "Olivia Dean Man I Need", "Keli Holiday", "Ball Park Music"], "2025-09-01 2026-01-15"),
         (["Spacey Jane Booster Seat", "Glass Animals Heat Waves", "Ball Park Music Cherub"], "2020-09-01 2021-01-18")]
for kw, tf in tests:
    try:
        t.build_payload(kw, geo="AU", timeframe=tf)
        df = t.interest_over_time()
        res[" | ".join(kw)] = {"ok": True, "rows": len(df), "mean": {k: round(float(df[k].mean()), 1) for k in kw},
                              "max": {k: int(df[k].max()) for k in kw}}
    except Exception as e:  # noqa: BLE001
        res[" | ".join(kw)] = {"ok": False, "error": repr(e)[:300]}
    time.sleep(20)
(OUT / "trends.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
