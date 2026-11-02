# scrapers2026

Goal: **2026 U.S. Senate (Ohio) results by county, split by vote method**
(Election Day, early in-person, mail, provisional), for all 88 counties.

## Start here

- **Which counties have what:** [COUNTIES.md](COUNTIES.md), all 88 counties
  with where each one's vote-method split comes from, where its scraper runs,
  how its labels map, and the evidence behind each verdict. In short: 21
  counties are scraped by vote method, Allen joins when it posts, 8 more might
  split on election night, 21 split only in the official canvass weeks later,
  and the rest are totals only.
- **Election night:** the [runbook](#election-night-runbook-nov-3-2026-times-et) below.
- **How we got here (research log):** [REPORT.md](REPORT.md), dated entries.
  Where an older entry disagrees with COUNTIES.md, COUNTIES.md is current.

Every county has Senate **totals** from the SOS statewide site. The work in
this repo is about the vote-method **split**, which only county sources have.

## Where things are

| What | Where | Notes |
|---|---|---|
| Per-county registry (machine-readable) | `counties.csv` | One row per county: FIPS, BOE site, platform, feed URLs, status, `history_split` verdict and evidence. Source for COUNTIES.md |
| Per-county status (human-readable) | `COUNTIES.md` | Generated: `python -m tools.make_counties_md` |
| One county's scraper | `counties/<county>/scraper.py` | Writes `output/summary_wide_latest.csv` (git-ignored) and `data/summary_wide.csv` (committed on change) |
| Combined Senate results | `results/senate_by_method.csv`, `results/senate_by_method_wide.csv` | Built by `python -m common.senate` from every `counties/*/data/` file plus the statewide totals. The Actions bot rebuilds them on election night |
| Statewide county totals (all 88, no split) | `results/senate_statewide_by_county.csv` | `python -m common.ohio_statewide` (headed Chromium; local only, blocked in Actions) |
| Vote-label → method mapping | `common/senate.py` (`METHOD_MAP`, `EV_METHOD_MAP`) and the Buckets column of COUNTIES.md | Assumptions and unmapped labels are listed per county in COUNTIES.md |
| Shared parsers | `common/` | `ohio_enr.py` (Ohio ENR XML/CSV), `enhanced_voting.py`, `clarity.py`, `pdf_results.py` (PDF layouts), `sos_browser.py` (reads SOS files through a real Chrome window), `ohio_statewide.py` |
| Research outputs | `tools/*.json` | `survey60_verdicts.json` and `past_reports.json` (past-report checks, with document URLs and excerpts), `county_survey.json` (site crawl), `enr_discovery.json` (SOS ENR election IDs), `clarity_probe.json` |
| Research and election-night tools | `tools/*.py`, `tools/*.sh` | `local_loop.sh` (election-night loop), `sos_chrome.sh`, `recheck_zero_reports.py`, `make_pdf_scraper.py`, `make_sos_scrapers.py`, `discover_enr.py`, `survey_counties.py`, `past_reports.py`, `build_method_workbook.py`, `make_counties_md.py` |
| GitHub Actions schedule | `.github/workflows/election-night.yml` | Scrapes the 7 counties reachable from Actions every 5 min (6 PM Nov 3 to 8 AM Nov 4 ET) and rebuilds `results/` |
| Tests | `tests/` | `python -c "import tests.test_build_method_workbook as t; t.test_buckets()"` (pytest not required) |

**Not in git, on purpose:**

| What | Where | Why |
|---|---|---|
| Vote-method workbook for the Google Sheet (`OH_Senate_2026_vote_method.xlsx` + `votes_by_method.csv`, `votes_long.csv`, `sources.csv`) | `../exports/` next to the clone on the loop machine | Rebuilt every loop cycle by `python -m tools.build_method_workbook ../exports`; anyone can rebuild it from the repo. Kept separate from the AP-based county aggregator; joins on `county_fips` |
| Each scraper run's timestamped files | `counties/*/output/` | Run history; only `data/summary_wide.csv` is committed |
| Past result PDFs used as evidence | The county and SOS URLs recorded in `tools/past_reports.json` and `tools/survey60_verdicts.json` | Public documents; SOS-hosted ones need a real browser to download |
| SOS Chrome profile | `~/.scrapers2026-chrome` | Browser state for `tools/sos_chrome.sh` |
| GitHub token | Typed into `tools/local_loop.sh` at start, held in memory only | Never written to disk or git config |

## Why some counties run on a Mac, not in Actions

The SOS-hosted sites (liveresults.boe.ohio.gov, www.boe.ohio.gov,
liveresults.ohiosos.gov) put a Cloudflare challenge in front of every script,
headless browser and GitHub runner, and their vote-method files sit behind a
Turnstile check. The repo owner waived the no-bypass rule for a real browser:
`tools/sos_chrome.sh` opens an ordinary Chrome window, and
`common/sos_browser.py` reads SOS files through it (same-origin fetch over
the Chrome DevTools port, 3 s apart). So the SOS ENR counties, the PDF
counties and the statewide totals run in `tools/local_loop.sh` on the owner's
Mac, which commits and pushes them every 5 minutes. Counties on other hosts
(Cuyahoga, Franklin, Hamilton, Montgomery, Summit, Pickaway, Hocking) run in
Actions.

```bash
tools/sos_chrome.sh                      # opens the SOS Chrome window; leave it open
tools/local_loop.sh                      # asks for a GitHub token once; every 5 min until 8 AM ET Nov 4
DRY_RUN=1 ONCE=1 tools/local_loop.sh     # test: one cycle, no git writes
```

Each cycle: SOS and PDF county scrapers (`python -m tools.run_sos_counties`),
statewide totals, commit and push only those files, pull the bot's commits,
then rebuild the vote-method workbook. The token needs Contents: Read and
write.

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
| Every loop cycle (automatic) | `tools/local_loop.sh` step 4 runs `tools.build_method_workbook ../exports` | Rebuilds the standalone vote-method sheet (`OH_Senate_2026_vote_method.xlsx` + one CSV per tab: votes_by_method, votes_long, sources) after pulling the bot's latest. Re-import into the Google Sheet when you want to update it. `fetched_at` shows when each county's numbers were fetched. Separate from the AP aggregator; joins on `county_fips`. Run it by hand any time with the same command |
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
3. If its source is reachable from GitHub Actions, add the name to `COUNTIES`
   in the workflow. If it needs the SOS Chrome window, `tools/local_loop.sh`
   runs it instead (through `tools/run_sos_counties.py`): SOS-hosted ENR
   counties are picked up from `tools/enr_discovery.json` (generate the
   scraper with `tools/make_sos_scrapers.py`); any other scraper declares
   `NEEDS_LOCAL_CHROME = True` (e.g. PDFs on www.boe.ohio.gov, generated by
   `tools/make_pdf_scraper.py`).
4. Update the county's row in `counties.csv` (status `working`, platform,
   results page), add its label mapping to `SCRAPED` in
   `tools/build_method_workbook.py`, then run `python -m tools.make_counties_md`.
