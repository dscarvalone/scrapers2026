# scrapers2026

Goal: **2026 U.S. Senate (Ohio) results by county, itemized by vote method.**

The combined result lives in `results/`:

- `senate_by_method_wide.csv`: one row per county and candidate, a column per
  vote method, plus total and precincts reported
- `senate_by_method.csv`: the same data with one row per county, candidate and
  method, including each county's original label for the method

Each county's scraper pulls that county's full results feed; `common/senate.py`
extracts the Senate race and maps vote methods to common names:

| Common method | County labels |
|---|---|
| Election Day | Election Day |
| Early In-Person | Early In-Person (Cuyahoga), Early Voting (ENR XML/CSV, incl. Franklin) |
| Mail | Vote By Mail (Cuyahoga), Mail Ballots (ENR XML), Absentee Ballots (Franklin; assumed to be mail, see REPORT.md) |
| Absentee (early in-person + mail) | Absentee (ENR CSV; not split by the county) |
| Provisional | Provisional |
| Post Election Day, Post VBM | Cuyahoga only, kept as reported |

A blank cell means that county doesn't report that method. Build it locally with
`python -m common.senate` (or `--from-output` after running scrapers locally).

## Layout

```
counties/
  <county>/
    scraper.py   # the scraper for that county
    README.md    # source, output format, notes
    data/        # results committed by automation (tracked)
    output/      # local run output (git-ignored)
common/
  ohio_enr.py    # shared parser for Ohio's liveresults.boe.ohio.gov feed (XML or CSV)
  senate.py      # combines all counties into results/ (Senate race by vote method)
results/         # the deliverable
.github/workflows/
  election-night.yml  # runs every county every 5 min on election night
```

## Counties

| County | Status | Source |
|---|---|---|
| [Cuyahoga](counties/cuyahoga/) | Working live, scheduled | Enhanced Voting Excel export |
| [Franklin](counties/franklin/) | Working live, scheduled | County-hosted ENR (liveresults.franklincountyohio.gov), XML then CSV |
| [Warren](counties/warren/) | Blocked, not scheduled | SOS-hosted ENR, Cloudflare challenge |
| [Butler](counties/butler/) | Blocked, not scheduled | SOS-hosted ENR, Cloudflare challenge |

The SOS-hosted feed (liveresults.boe.ohio.gov), which most Ohio counties use,
blocks scripts behind Cloudflare, and its vote-method files sit behind a
Turnstile CAPTCHA. For the other 86 counties, `common/ohio_statewide.py`
gets county **totals** (no method split) from the SOS statewide site using a
headed Chromium:

```bash
python -m playwright install chromium     # once
python -m common.ohio_statewide           # writes results/senate_statewide_by_county.csv
python -m common.senate                   # merges it: "Not split by method" column
```

See REPORT.md.

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
After scraping it rebuilds `results/`; when anything changes it commits each
county's `data/summary_wide.csv` and the results files, so the commit history
is a timeline of the count. If one county fails, the others
still run and the run is marked failed. Use "Run workflow" on the Actions tab
to run it manually.

## Adding a county

1. Create `counties/<name>/` with `__init__.py`, `scraper.py`, `README.md` and
   `data/.gitkeep`. The scraper must write `output/summary_wide_latest.csv`.
2. If the county uses Ohio's liveresults.boe.ohio.gov feed, the scraper is just
   its URL(s) plus a call to `common.ohio_enr.run` (see `counties/warren/` or
   `counties/butler/`). Both the summary XML and CSV are supported.
3. Add the name to `COUNTIES` in the workflow.
