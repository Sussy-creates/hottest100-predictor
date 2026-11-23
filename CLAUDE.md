# Notes for Claude

- Goal: predict the triple j Hottest 100 #1 and top-10 set from popularity signals only (triple j airplay, Spotify AU, Shazam AU). Top-5 order is a readout, not a target.
- Plan doc: https://claude.ai/artifact/4Dmt6QUCEukNZGmEhdvuoZ (read with the docs tools, never web-fetch).
- The coding sandbox cannot reach the data sites (ABC API, kworb, Wayback). Do all fetching in GitHub Actions workflows that commit results under `data/`. Do not try to route around the sandbox allowlist.
- Training years: countdowns 2015–2024. Holdout: 2025 countdown. Never build, plot or inspect 2025 features/results before the rule is frozen in tag `rule-v1`.
- Snapshots are anchored to each year's voting close (T−120/−90/−60/−30/0 days), never calendar months.
- Normalise features as within-year percentiles among that year's candidates.
- Keep raw data immutable in `data/raw/`; derived tables go in `data/derived/`.
