"""Parse archived chart pages (kworb tables, old shazam.com pages) into rank / artist / title rows."""
from __future__ import annotations

import gzip
import html as htmllib
import json
import re
from pathlib import Path

import pandas as pd

ROW = re.compile(r"<tr[^>]*>(.*?)(?=<tr[\s>]|</tbody>|</table>|$)", re.S | re.I)  # kworb leaves header rows unclosed
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
NUM = re.compile(r"^[+-]?[\d,]+$")


def _text(c: str) -> str:
    return htmllib.unescape(TAG.sub(" ", c)).strip().replace("\xa0", " ")


def parse_kworb(page: str) -> pd.DataFrame:
    rows = []
    for tr in ROW.findall(page):
        cells = [_text(c) for c in CELL.findall(tr)]
        if not cells or not cells[0].isdigit():
            continue
        text_i = next((i for i, c in enumerate(cells) if " - " in c), None)
        if text_i is None:
            continue
        artist, title = cells[text_i].split(" - ", 1)
        nums = [int(c.replace(",", "")) for c in cells[text_i + 1:] if NUM.match(c.replace(" ", ""))]
        rows.append({"rank": int(cells[0]), "artist": re.sub(r"\s+", " ", artist).strip(),
                     "title": re.sub(r"\s+", " ", title).strip(), "value": nums[0] if nums else None})
    return pd.DataFrame(rows)


def parse_shazam_old(page: str) -> pd.DataFrame:
    """Old shazam.com Top 100 pages (2014-2016): one <article data-chart-position=N> per track, with the title in
    the ti__title content attribute and the artist in the byArtist meta name."""
    rows = []
    for block in page.split("<article")[1:]:
        pos = re.search(r'data-chart-position="(\d+)"', block)
        title = re.search(r'class="ti__title"[^>]*content="([^"]*)"', block)
        artist = re.search(r'itemprop="byArtist"[^>]*>\s*<meta itemprop="name" content="([^"]*)"', block)
        if pos and title and artist:
            rows.append({"rank": int(pos.group(1)), "title": htmllib.unescape(title.group(1)).strip(),
                         "artist": htmllib.unescape(artist.group(1)).strip(), "value": None})
    return pd.DataFrame(rows)


def load_captures(folder: Path, parser) -> pd.DataFrame:
    """Every capture in a folder -> long table with the capture date (UTC, from the Wayback timestamp)."""
    out = []
    for f in sorted(folder.glob("*.html.gz")):
        page = gzip.decompress(f.read_bytes()).decode("utf-8", "replace")
        df = parser(page)
        if len(df):
            stamp = f.name.split(".")[0]
            df["captured"] = pd.to_datetime(stamp[:14] if stamp[:4].isdigit() and len(stamp) >= 8 else stamp,
                                            format="%Y%m%d%H%M%S" if len(stamp) >= 14 else None, errors="coerce")
            out.append(df)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
