# Hottest 100 Predictor

Predicts the triple j Hottest 100 **#1 and top 10** from popularity trajectories measured before voting closes. Popularity signals only: no vote scraping, no X/Twitter, no LLM training.

Plan: [Hottest 100 Predictor — Build Plan](https://claude.ai/artifact/4Dmt6QUCEukNZGmEhdvuoZ)

## Design in one paragraph

Three signals (triple j airplay, Spotify AU daily streams, Shazam AU chart) are snapshotted at T−120, T−90, T−60, T−30 and T−0 days before each year's voting close. Features describe trajectory shape (cumulative level, liftoff, velocity, acceleration, fade, artist vote-splitting), normalised as within-year percentiles. A transparent weighted rule is the primary model; a logistic regression and an XGBoost ranker are the check. Training: countdowns 2015–2024, leave-one-year-out. Holdout: the 2025 countdown, scored once after the rule is frozen.

## Where things run

All network fetching runs on **GitHub Actions**, which has open internet. The coding sandbox used to write this code cannot reach the data sites. Workflows fetch raw data and commit it back under `data/`.

| Workflow | Does |
| --- | --- |
| `probe.yml` | One-off check of every data source: reachability, history depth, response schema, Wayback snapshot counts |

## Layout

```
config/       countdown calendar (voting close, eligibility window per year)
data/raw/     source data exactly as fetched (committed by Actions)
data/probe/   source-availability checks
scripts/      entry points run by workflows
src/h100/     library code: ingestion, matching, features, scoring
```

## Holdout rule

No 2025-countdown features or results are built or inspected until the scoring rule is frozen in a tagged commit (`rule-v1`).
