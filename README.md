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

Some SOS-hosted counties do publish the vote-method split in their ENR
summary XML. Those files load in an ordinary Chrome window but not for
scripts, so `common/sos_browser.py` reads them through a Chrome window you
open (`tools/sos_chrome.sh`). `tools/discover_enr.py` found each such
county's Nov 3 election ID (`tools/enr_discovery.json`), and
`tools/make_sos_scrapers.py` generated their `counties/<name>/` scrapers.

The SOS sites block GitHub Actions, so on election night run the local loop
from a desktop, in a normal Terminal window:

```bash
tools/sos_chrome.sh                      # opens the SOS Chrome window; leave it open
tools/local_loop.sh                      # asks for a GitHub token once; every 5 min until 8 AM ET Nov 4
DRY_RUN=1 ONCE=1 tools/local_loop.sh     # test: one cycle, no git writes
```

Each cycle runs the SOS county scrapers (`python -m tools.run_sos_counties`)
and the statewide fetch, then commits and pushes only those files. The
workflow's combine step merges everything on the next bot run. The token
needs Contents: Read and write.

## Election night runbook (Nov 3, 2026, times ET)

All commands run from the repo root in a normal Terminal window, not from an
agent sandbox. Keep the Mac plugged in and online.

| When | Do | Expect |
|---|---|---|
| Before 6:00 PM | `git pull` | Picks up the bot's and the loop's commits |
| 6:00 PM | Actions schedule starts (every 5 min) | Cuyahoga, Franklin, Montgomery, Summit, Hamilton, Pickaway and Hocking scraped in Actions |
| 7:00 PM | `tools/sos_chrome.sh` | A separate Chrome window opens on Butler's ENR page. If it shows "Verify you are human", click it. Leave it open all night |
| 7:00 PM | `tools/local_loop.sh` (enter token once) | Every 5 min: SOS ENR + PDF counties + statewide totals, commit, push. Allen logs "not posted yet" until its link appears |
| ~8:30 PM, after the first absentee uploads | In a second Terminal tab: `.venv/bin/python -m tools.recheck_zero_reports --make-scrapers` | Lists every still-unknown SOS-hosted county as no_file / total_only / SPLIT, and writes scrapers for the SPLIT ones (the loop picks them up next cycle). Takes ~5 min |
| ~9:30 PM | Run the recheck again, then commit the new scraper folders: `git add counties/ && git commit -m "Election-night recheck: new counties" && git push origin main` (or let the loop push on its next commit) | Catches counties that post later |
| Any time | Spot-check `results/senate_by_method_wide.csv` on GitHub | `source` column: `county_feed` (by method) or `sos_statewide` (totals only) |
| Any time | `.venv/bin/python -m tools.build_method_workbook ../exports` | Rebuilds the standalone vote-method sheet (`OH_Senate_2026_vote_method.xlsx` + one CSV per tab: votes_by_method, votes_long, sources). Re-import into the Google Sheet. Separate from the AP aggregator; joins on `county_fips` |
| 8:00 AM Nov 4 | Loop and schedule stop on their own | |

The recheck lists counties whose BOE site isn't SOS-hosted for a manual
look (their election-night address isn't predictable): Ottawa, Sandusky,
Crawford, Guernsey, Hancock, Henry, Mercer, Morrow, Union, Williams,
Clermont, Delaware, Lake, Lorain, Mahoning, Portage, Trumbull, Wayne, Wood.
The most promising are **Clermont, Lake and Ottawa**, whose official
reports split votes. If one posts a split PDF, add it with
`python -m tools.make_pdf_scraper "<County>" positional "<columns>"`, then
edit `URL`/`PAGE` in the generated `scraper.py` to the county's link.

If something breaks:
- **"SOS Chrome window not open"** in the loop log: rerun `tools/sos_chrome.sh`.
- **"Cloudflare check"**: click the check in that Chrome window; the next cycle retries.
- **HTTP 429**: the loop backs off on its own. Don't restart it.
- **A county's URL changes**: fix `URL` in `counties/<county>/scraper.py` and push. The others keep running.
- **The loop dies**: rerun `tools/local_loop.sh`. It pulls first, then carries on.

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
