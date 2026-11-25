"""Per-recording artist metadata from the raw ABC log: is_australian (any primary artist flagged) and artist ids."""
import gzip, json
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
rows = {}
for f in sorted((ROOT / "data/raw/abc_plays").rglob("*.jsonl.gz")):
    with gzip.open(f, "rt") as fh:
        for line in fh:
            d = json.loads(line)
            rid = d.get("recording_id")
            if not rid or rid in rows:
                continue
            arts = d.get("artists") or []
            prim = [a for a in arts if a.get("type") == "primary"] or arts
            flags = [a.get("is_australian") for a in prim]
            rows[rid] = {"recording_id": rid,
                         "aus_any": any(x is True for x in flags),
                         "aus_known": any(x is not None for x in flags),
                         "artist_ids": "|".join(a["id"] for a in prim if a.get("id"))}
out = pd.DataFrame(rows.values())
out.to_parquet(ROOT / "data/derived/recording_meta.parquet", index=False)
print(len(out), out.aus_any.mean().round(3), out.aus_known.mean().round(3))
