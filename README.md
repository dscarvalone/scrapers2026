# scrapers2026

Election results scrapers, organized by county.

## Layout

```
counties/
  <county>/
    scraper.py   # the scraper for that county
    README.md    # source, output format, notes
    data/        # results committed by automation (tracked)
    output/      # local run output (git-ignored)
.github/workflows/
  <county>.yml   # scheduled runs for that county
```

## Counties

| County | Status | Source |
|---|---|---|
| [Cuyahoga](counties/cuyahoga/) | Working, scheduled for election night | Enhanced Voting Excel export |
| [Franklin](counties/franklin/) | Source identified, data feed not yet found | vote.franklincountyohio.gov |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Run any county from the repo root:

```bash
python -m counties.<county>.scraper
```
