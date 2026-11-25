"""All countdown results 2005-2025 in one table, for artist-history features (ranks known before each vote)."""
import json, sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from parse_results import results
out = []
for f in sorted((ROOT / "data/raw/wikipedia").glob("*.json")):
    df = results(int(f.stem), json.loads(f.read_text())["text"]); out.append(df)
    print(f.stem, len(df), df["rank"].max())
pd.concat(out).to_csv(ROOT / "data/derived/results_history.csv", index=False)
