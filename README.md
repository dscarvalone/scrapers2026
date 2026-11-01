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
