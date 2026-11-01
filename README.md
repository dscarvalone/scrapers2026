# scrapers2026

A collection of web scrapers.

## Layout

- `scrapers/` — one module per scraper
- `output/` — scraped data (git-ignored)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
python -m scrapers.<scraper_name>
```

## Scrapers

### `cuyahoga` — Cuyahoga County, OH election results by vote type

Downloads the county's "All Results" Excel export and outputs each contest and
choice split by vote type: Election Day, Early In-Person, Vote By Mail,
Provisional, Post Election Day, and Post VBM, plus a total. Rows for Ballots
Cast, Over Votes, and Under Votes are kept and marked in `row_type`. Each run
checks that the vote-type sums match the county's own totals.

```bash
python -m scrapers.cuyahoga               # county-wide, wide format
python -m scrapers.cuyahoga --precincts   # adds precinct level (~160k rows, ~1 min)
python -m scrapers.cuyahoga --long        # one row per vote type
python -m scrapers.cuyahoga --file x.xlsx # parse a local copy
python -m scrapers.cuyahoga --url <url>   # if the county posts a new file URL
```

Output goes to `output/cuyahoga/` as `<name>_latest.csv` plus a timestamped copy
per run.

#### Election-night automation

`.github/workflows/cuyahoga-election-night.yml` runs the scraper every 5 minutes
from 6 PM ET on Nov 3, 2026 to 8 AM ET on Nov 4. Whenever results change, it
commits `data/cuyahoga/summary_wide.csv` (so the commit history doubles as a
timeline of results) and attaches the precinct CSV to that run as a download,
kept for 3 days. Use the "Run workflow" button on the Actions tab to run it
manually at any time.
