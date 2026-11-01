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
common/
  ohio_enr.py    # shared parser for Ohio's liveresults.boe.ohio.gov feed
.github/workflows/
  election-night.yml  # runs every county every 5 min on election night
```

## Counties

| County | Status | Source |
|---|---|---|
| [Cuyahoga](counties/cuyahoga/) | Working, scheduled for election night | Enhanced Voting Excel export |
| [Warren](counties/warren/) | Working, scheduled for election night | Ohio ENR summary XML (liveresults.boe.ohio.gov) |
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

## Election-night automation

`.github/workflows/election-night.yml` runs every county listed in its
`COUNTIES` setting every 5 minutes from 6 PM ET Nov 3, 2026 to 8 AM ET Nov 4.
When results change it commits each county's `data/summary_wide.csv`, so the
commit history is a timeline of the count. If one county fails, the others
still run and the run is marked failed. Use "Run workflow" on the Actions tab
to run it manually.

## Adding a county

1. Create `counties/<name>/` with `__init__.py`, `scraper.py`, `README.md` and
   `data/.gitkeep`. The scraper must write `output/summary_wide_latest.csv`.
2. If the county uses Ohio's liveresults.boe.ohio.gov feed, the scraper is just
   a URL plus a call to `common.ohio_enr.run` (see `counties/warren/`).
3. Add the name to `COUNTIES` in the workflow.
