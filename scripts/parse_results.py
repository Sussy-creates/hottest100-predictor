"""Parse countdown results (ranks 1-200) and voting/eligibility text from the Wikipedia pages.

Training years -> data/derived/results.csv and data/derived/voting_text.csv
Holdout year   -> data/holdout/results_2025.csv (never printed; see CLAUDE.md)
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wikipedia"
HOLDOUT_YEAR = 2025
KEYWORDS = re.compile(r"\bvot(e|es|ing)\b.*\b(open|clos|commenc|began|begin|end)|eligib|premiered|released between", re.I)


def results(year: int, html: str) -> pd.DataFrame:
    frames = []
    for t in pd.read_html(io.StringIO(html)):
        t.columns = [re.sub(r"\[\d+\]", "", str(c)).strip() for c in t.columns]  # "Song[1]" -> "Song"
        cols = list(t.columns)
        if {"#", "Song", "Artist"} <= set(cols):
            t = t.rename(columns={"#": "rank", "Song": "song", "Artist": "artist",
                                  "Country of origin": "country"})
            t["rank"] = pd.to_numeric(t["rank"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
            frames.append(t[[c for c in ("rank", "song", "artist", "country") if c in t.columns]])
    df = pd.concat(frames).dropna(subset=["rank"]).drop_duplicates("rank")
    df["rank"] = df["rank"].astype(int)
    df["song"] = df["song"].astype(str).str.strip().str.strip('"').str.strip("“”")
    df.insert(0, "countdown_year", year)
    return df.sort_values("rank")


def voting_sentences(year: int, html: str) -> list[dict]:
    text = BeautifulSoup(html, "lxml").get_text(" ")
    text = re.sub(r"\[\d+\]|\[citation needed\]", "", re.sub(r"\s+", " ", text))
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [{"countdown_year": year, "sentence": s.strip()} for s in sents if KEYWORDS.search(s) and len(s) < 400]


def main() -> None:
    (ROOT / "data" / "derived").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "holdout").mkdir(parents=True, exist_ok=True)
    train, votes = [], []
    for f in sorted(RAW.glob("*.json")):
        year = int(f.stem)
        html = json.loads(f.read_text())["text"]
        df = results(year, html)
        if year == HOLDOUT_YEAR:
            df.to_csv(ROOT / "data" / "holdout" / f"results_{year}.csv", index=False)
            pd.DataFrame(voting_sentences(year, html)).to_csv(
                ROOT / "data" / "holdout" / f"voting_text_{year}.csv", index=False)
            print(f"{year}: holdout, {len(df)} rows written, not shown")
            continue
        train.append(df)
        votes += voting_sentences(year, html)
        gaps = sorted(set(range(1, df["rank"].max() + 1)) - set(df["rank"]))
        print(f"{year}: {len(df)} rows, ranks 1-{df['rank'].max()}, missing ranks {gaps[:10]}")
    pd.concat(train).to_csv(ROOT / "data" / "derived" / "results.csv", index=False)
    pd.DataFrame(votes).to_csv(ROOT / "data" / "derived" / "voting_text.csv", index=False)


if __name__ == "__main__":
    main()
