# Notes for Claude

- Goal: predict the triple j Hottest 100 #1 and top-10 set from popularity signals only (triple j airplay, Spotify AU, Shazam AU). Top-5 order is a readout, not a target.
- Plan doc: https://claude.ai/artifact/4Dmt6QUCEukNZGmEhdvuoZ (read with the docs tools, never web-fetch).
- The coding sandbox cannot reach the data sites (ABC API, kworb, Wayback). Do all fetching in GitHub Actions workflows that commit results under `data/`. Do not try to route around the sandbox allowlist.
- Training years: countdowns 2015–2024. Holdout: 2025 countdown. Never build, plot or inspect 2025 features/results before the rule is frozen in tag `rule-v1`.
- Snapshots are anchored to each year's voting close (T−120/−90/−60/−30/0 days), never calendar months.
- Normalise features as within-year percentiles among that year's candidates.
- Keep raw data immutable in `data/raw/`; derived tables go in `data/derived/`.
- Spotify AU sources (`data/raw/spotify_au/`): `gonzalopezgil` = daily top 200 with streams, 2017-01-01 onward, every day present (primary). `jfreyberg__charts` = weekly top 200, 2013–2023 (the only source for the 2015–16 countdowns). `dhruvildave` = daily 2017–2021, cross-check only.
- Compute Spotify features on weekly aggregates for every year, so 2015–16 (weekly-only) and later years are comparable.
- triple j airplay (`data/raw/abc_plays/`): one slimmed play per line, Dec 2014 onward; `recording_id` and artist `id` are stable ABC IDs.
- Results: `data/derived/results.csv` = ranks 1–200 for training countdowns 2015–2024 (from Wikipedia). 2025 results sit in `data/holdout/` and must not be opened before `rule-v1`.
- Countdown calendar: `config/countdowns.csv` (voting open/close, eligibility window Dec 1–Nov 30, source per row). 2015–16 close dates are day-only; others carry the AEDT close time.
- Leakage: the countdown broadcast pushes songs onto Spotify (12 of the 100 training top-10 songs first charted in countdown week). Every feature must use data up to voting close only; for weekly Spotify, only weeks ending on or before close.
- Song matching (`scripts/build_songs.py`, `src/h100/normalize.py`): triple j recordings merge into songs by title key + version (lav/live/'') + artist overlap. Spotify matches always require artist overlap (title-only Spotify matches were all wrong artists). Some countdown entries were never played on triple j before close; they keep zero airplay rather than being dropped.
