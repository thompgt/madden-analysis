# Madden NFL 26 Player Analysis

A data science project on Madden NFL 26 in-game player ratings: demographics, how well Madden ratings
proxy real-world NFL ability (validated against 2025 season stats and Over The Cap contract data), and
position/archetype profiling — modeled on the sibling `fifa-analysis` project's approach to EA FC 26
ratings.

## Data sources

- **Madden NFL 26 ratings**: [`flynn28/madden-26-week-15-player-ratings`](https://www.kaggle.com/datasets/flynn28/madden-26-week-15-player-ratings)
  on Kaggle (~2,015 rostered players as of the Week 15 2025-season roster update). This dataset has full
  per-attribute breakdowns (speed, awareness, throw power, route running, block shedding, etc.), not just
  an overall rating, so it was used directly rather than falling back to scraping madden.tools or
  nflDraftBuzz.
- **2025 NFL stats**: pulled via [`nflreadpy`](https://github.com/nflverse/nflreadpy) (the nflverse
  ecosystem's Python client) — season-total per-player box score stats and advanced/EPA-based metrics,
  `scripts/fetch_nfl_data.py`.
- **Contract/salary data (market-value analog)**: also pulled via `nflreadpy`'s `load_contracts()`, which
  is itself sourced from Over The Cap. This meant a separate `scrape_salary.py` targeting Spotrac/OTC
  directly wasn't necessary — OTC's contract data (APY, guarantees, cap %) is already available as a
  clean, structured table through the same library used for stats, and is the closest analog to
  fifa-analysis's Transfermarkt market-value check.
- **Team name crosswalk**: `nflreadpy`'s `load_teams()` and `load_players()`, used to reconcile Madden's
  full team names, nflverse's stat-table team abbreviations, and OTC's team nicknames into one matching key.

No scraping of madden.tools/nflDraftBuzz or Spotrac/OTC directly was needed — both the ratings and the
salary/performance data were available through clean, purpose-built APIs (Kaggle + nflreadpy), so this
project didn't need to fall back to HTML scraping at all.

## Project structure

```
scripts/                  data acquisition + processing pipeline
  fetch_madden.py          downloads the Madden 26 Kaggle dataset
  fetch_nfl_data.py         pulls 2025 stats, player bios, contracts, and team crosswalk via nflreadpy
  build_dataset.py          fuzzy-matches Madden ratings to real stats/contracts into one player table
data/
  raw/                     untracked, gitignored (regenerate via scripts/)
  processed/               small merged/cleaned CSVs, tracked in git
notebooks/
  01_demographics.ipynb        who plays: age, position, college, height/weight, experience, handedness
  02_rating_validation.ipynb   Madden ratings vs real 2025 stats (EPA-based) and contract value (APY)
```

## Reproducing

```
pip install -r requirements.txt
python scripts/fetch_madden.py
python scripts/fetch_nfl_data.py
python scripts/build_dataset.py
jupyter notebook
```

Kaggle API credentials must be set via `KAGGLE_USERNAME`/`KAGGLE_KEY` env vars (or `~/.kaggle/kaggle.json`)
to run `fetch_madden.py`. `fetch_nfl_data.py` needs no auth — nflverse's data releases are public.

## Matching methodology

Madden, nflreadpy's stats, and OTC's contracts each use different name/team formats and have no shared
player ID, so `build_dataset.py` fuzzy-matches (rapidfuzz, `token_sort_ratio`, threshold 85) blocked by
team + a broad position group (`QB`, `RB`, `WR`, `TE`, `OL`, `EDGE`, `DL`, `LB`, `DB`, `ST`). Because all
three sources describe the same single league's current active rosters (~53 players/team, no
international transfers or multi-league fragmentation to worry about), this reaches a ~76% match rate to
real stats and ~68% to an active contract — much higher than fifa-analysis's ~9%/~3% cross-league soccer
match rates against Transfermarkt/Sofascore.
