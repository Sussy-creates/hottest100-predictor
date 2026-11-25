"""Google Trends AU interest for each target artist in the 60 days before close, relative to the anchor term
"triple j" in the same request (so values compare across batches). Writes data/probe/trends_targets.csv."""
import csv, time
from datetime import date, timedelta
from pathlib import Path
from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = "triple j"
rows = list(csv.DictReader(open(ROOT / "data/probe/pageview_targets.csv")))
t = TrendReq(hl="en-AU", tz=-600, retries=3, backoff_factor=10)
by_year: dict = {}
for r in rows:
    by_year.setdefault((r["countdown_year"], r["close"]), set()).add(r["artist_name"])
vals: dict = {}
for (y, close), names in sorted(by_year.items()):
    c = date.fromisoformat(close); tf = f"{c - timedelta(days=60):%Y-%m-%d} {c - timedelta(days=1):%Y-%m-%d}"
    names = sorted(names)
    for i in range(0, len(names), 4):
        kw = names[i:i + 4] + [ANCHOR]
        for attempt in range(3):
            try:
                t.build_payload(kw, geo="AU", timeframe=tf, cat=35)  # category 35 = Music & Audio
                df = t.interest_over_time()
                a = float(df[ANCHOR].mean()) or 1e-9
                for k in kw[:-1]:
                    vals[(y, k)] = (float(df[k].mean()), float(df[k].mean()) / a)
                break
            except Exception as e:  # noqa: BLE001
                print(y, kw, "error", repr(e)[:120], flush=True); time.sleep(60 * (attempt + 1))
        time.sleep(15)
    print(y, "done", flush=True)
for r in rows:
    raw, rel = vals.get((r["countdown_year"], r["artist_name"]), ("", ""))
    r["trends_mean"], r["trends_rel_anchor"] = raw, rel
with open(ROOT / "data/probe/trends_targets.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
