"""Cleaner Australian flag. The ABC API marks ~10% of non-Australian countdown artists as Australian
(The Wombats, Disclosure, Billie Eilish...). Where the lead artist appeared in an EARLIER countdown, use the
country Wikipedia gives there; otherwise keep the ABC flag. Earlier years only, so no outcome leakage."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from history import lead


def aus_fixed(f: pd.DataFrame) -> pd.Series:
    h = pd.read_csv(ROOT / "data/derived/results_history.csv")
    h["lead"] = h.artist.map(lead)
    h["aus"] = h.country.astype(str).str.contains("Australia").astype(int)
    h = h.sort_values("countdown_year")
    out = []
    for y, l, abc in zip(f.countdown_year, f.artist.map(lead), f.is_aus):
        prev = h[(h.countdown_year < y) & (h.lead == l)]
        out.append(prev.aus.iloc[-1] if len(prev) else abc)
    return pd.Series(out, index=f.index, dtype=float)


if __name__ == "__main__":
    from harness import loyo, metrics, summary, CORE_FEATURES
    from pairwise_fit import pw
    f = pd.read_parquet(ROOT / "data/derived/analysis_frame.parquet")
    f = f[f.snapshot == 0].copy()
    f["is_aus2"] = aus_fixed(f)
    print("changed flags:", int((f.is_aus2 != f.is_aus).sum()), "of", len(f))
    rows = []
    for seeds in ((1, 2, 3, 4, 7), (11, 12, 13, 14, 15)):
        m = metrics(loyo(f, CORE_FEATURES + ["is_aus2"], fitter=pw(seeds))); s = summary(m)
        s["name"] = "core+aus(fixed) pw"; s["seeds"] = str(seeds)
        s["per_year_top10"] = " ".join(map(str, m.top10)); s["per_year_winner"] = " ".join(str(int(x)) for x in m.winner_rank)
        print(s, flush=True); rows.append(s)
    pd.DataFrame(rows).to_csv(ROOT / "reports/aus_fix_test.csv", index=False)
