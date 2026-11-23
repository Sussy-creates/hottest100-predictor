"""Stream a large Spotify chart CSV (plain or zipped), keep Australian rows, report coverage.

Schema-agnostic: finds the country/region and date columns by name, so it works across the
different Kaggle dumps. Writes <out>.parquet (AU rows) and <out>.summary.json.

Usage: python scripts/extract_spotify_au.py <csv-or-zip> <out-stem> [--member NAME]
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

AU_VALUES = {"au", "australia"}


def open_csv(path: Path, member: str | None):
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.endswith(".csv")]
        name = member or names[0]
        return io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace"), name
    return open(path, encoding="utf-8", errors="replace"), path.name


def pick(cols: list[str], *needles: str) -> str | None:
    low = {c.lower(): c for c in cols}
    for n in needles:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--member")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    fh, name = open_csv(args.path, args.member)
    reader = pd.read_csv(fh, dtype=str, chunksize=500_000, on_bad_lines="skip")

    summary: dict = {"source_file": name, "rows_scanned": 0}
    country_col = date_col = None
    countries: Counter = Counter()
    keep, sample = [], None

    for chunk in reader:
        if sample is None:
            sample = chunk.head(5).to_dict(orient="records")
            cols = list(chunk.columns)
            summary["columns"] = cols
            country_col = pick(cols, "country", "region", "market")
            date_col = pick(cols, "date", "day")
            summary["country_col"], summary["date_col"] = country_col, date_col
        summary["rows_scanned"] += len(chunk)
        if country_col is None:
            break  # can't filter; the sample tells us the schema
        vals = chunk[country_col].fillna("")
        countries.update(vals.str.lower().value_counts().head(80).to_dict())
        au = chunk[vals.str.strip().str.lower().isin(AU_VALUES)]
        if len(au):
            keep.append(au)

    summary["sample_rows"] = sample
    summary["top_country_values"] = countries.most_common(15)
    if keep:
        df = pd.concat(keep, ignore_index=True)
        df.to_parquet(args.out.with_suffix(".parquet"), index=False)
        summary["au_rows"] = len(df)
        if date_col:
            d = pd.to_datetime(df[date_col], errors="coerce")
            summary["au_date_min"] = str(d.min().date()) if d.notna().any() else None
            summary["au_date_max"] = str(d.max().date()) if d.notna().any() else None
            summary["au_days_by_year"] = (
                d.dt.normalize().drop_duplicates().dt.year.value_counts().sort_index().to_dict()
            )
            if (cc := pick(list(df.columns), "chart")) and cc != date_col:
                summary["au_chart_values"] = df[cc].value_counts().head(10).to_dict()
    else:
        summary["au_rows"] = 0

    Path(str(args.out) + ".summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "sample_rows"}, indent=2, default=str))


if __name__ == "__main__":
    main()
