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

## Lessons from Nov 3, 2026 (read this first next cycle)

Written the morning after, for the next run (~Nov 2028). The county summary
and runbook further down are the **pre-election plan**; this section is what
actually happened and what to do differently.

### 1. Freeze the model's expectations before polls close

The single biggest gap of the night: we had no saved copy of the model's
**pre-election expectations by vote mode**, and the live sheet's fields
changed meaning during the count.

- **What to save, and when:** a copy of the DSCC election-night workbook's
  `county_raw` tab, at least the evening before, at 6:00 PM, and at 7:25 PM
  (before the first absentee release). Each copy should include, per county:
  - `expected_frozen_total_votes` and `expected_frozen_two_way` (overall;
    stay frozen all night).
  - `eday_exp_total_votes` and `early_exp_total_votes`. Expected Early is the
    literal count of early ballots submitted (in-person + mail), so it is
    known, not modeled.
  - `eday_exp_two_way`, `early_exp_two_way`, `evip_exp_two_way` and
    `vbm_exp_two_way`, plus the `*_exp_remaining_two_way` fields.
- **Why it matters:**
  - **Live fields stop being priors.** During the count, the live
    `early_exp_two_way` equaled counted + remaining, so it matched the actual
    by construction and was useless as a prior.
  - **Mode priors were incomplete.** In every copy we had (Oct 30 through
    Nov 2, 11:07 PM) they covered only 24 counties (15 for EVIP/VBM).
  - **The fix came late.** Someone fixed them for all 88 counties during the
    night; next time, confirm all 88 are filled **before** Election Day.
- **How:** download the workbook (File → Download → .xlsx) at those times
  and keep the files dated. Uploaded copies from 2026 were read with
  openpyxl, tab `county_raw`. Better: add a small script that reads the tab
  through the Sheets API (read-only) and writes
  `snapshots/model_<timestamp>.csv`, and run it from the loop until the
  first results.
- **Also freeze our own feed:** the loop's commits are the time series for
  our numbers (`git log -- counties/<c>/data/summary_wide.csv`;
  `tools/_eday_drift.py` replays a county's Eday batches from them).
  `results/statewide_snapshots.csv` is the SOS time series. Don't rewrite
  either.

### 2. Which counties split results by vote mode (actual, Nov 3, 2026)

Final state of the last build (`../exports/OH_Senate_2026_vote_method.xlsx`,
`county_results` tab, `method_source`):

| Outcome | Counties |
|---|---|
| **Own split, Early split into in-person and mail (18)** | Athens, Butler, Carroll, Clark, Clermont, Franklin, Greene, Licking, Lucas, Madison, Miami, Montgomery, Pickaway, Preble, Seneca, Stark, Summit, Warren |
| **Own split, Early combined (2)** | Erie, Hamilton |
| **Split exists but feed stuck (4)**: fell back to the SOS totals | Cuyahoga (until the bot's overnight runs), Hocking (EV election ID never found; endpoint returned 204), Paulding and Van Wert (PDF stayed the zero report all night) |
| **Waited for a link that never came** | Allen (PDF never posted; treated as first drop) |
| **Totals only, first-drop estimate (60)** | Adams, Allen, Ashland, Auglaize, Brown, Champaign, Clinton, Columbiana, Coshocton, Crawford, Darke, Defiance, Delaware, Fairfield, Fayette, Fulton, Gallia, Geauga, Guernsey, Hancock, Hardin, Henry, Highland, Holmes, Huron, Jackson, Jefferson, Knox, Lake, Lawrence, Logan, Lorain, Mahoning, Marion, Medina, Meigs, Mercer, Monroe, Morgan, Muskingum, Noble, Ottawa, Perry, Pike, Portage, Putnam, Richland, Ross, Sandusky, Scioto, Shelby, Trumbull, Tuscarawas, Union, Vinton, Washington, Wayne, Williams, Wood, Wyandot |
| **Totals only, no clean first drop (4)**: first report already had precincts | Ashtabula, Belmont, Harrison, Morrow |

The surprises:
- **Confirmed totals only by the election-day sweeps:** Portage, Lorain and
  Delaware.
- **None of the "likely" or "unknown" counties split on election night.**
  Tuscarawas, Darke, Auglaize, Logan, Coshocton, Union, Hancock, Knox and
  the rest all stayed totals only.
- **Gallia's precinct PDF has ballots cast by mode but no contests**, so it
  can't give a Senate split. Shelby, Highland and Putnam split only in their
  precinct PDFs, and the summing parser was never built.
- **Clermont posted copier scans** (image-only PDFs, no text layer). It's
  read by OCR now (`common/pdf_ocr.py`), checksum-gated: every cell must sum
  to the row total. Its file name changes with every update (`44of168.pdf`
  means 44 of 168 precincts in), and its label is year-first ("2026 November
  3 General Election - Unofficial Results").
- **Athens and Seneca** sat on zero reports for hours before updating.
- **Lucas posted nothing at all** through at least 10:30 PM, in either our
  feed or AP's. It's the largest blue county after Cuyahoga, Franklin and Hamilton.
- **Cuyahoga's .xlsx export stayed at the zero report.** We switched it to
  the Enhanced Voting JSON API
  (`app.enhancedvoting.com/results/public/api/elections/cuyahoga-county-oh/GE2026/data`).
  Its vote types include `Post Election Day` and `Post VBM`.
- **Butler lists named write-ins** (Faris, Holliman, Telymonde) as their own
  candidates. They now fold into Write-in with a warning.

Before next cycle, redo the past-report survey (`tools/past_reports.py`,
`tools/survey_counties.py`): sites, election IDs and file names all change.
Treat this table as the starting hypothesis, not the answer.

### 3. Pipeline lessons

- **GitHub Actions cron is not reliable on election night.**
  - **It ran late or not at all.** The scheduled bot didn't commit from
    Nov 1 until after midnight on Nov 4, then committed at 12:58 AM and
    9:21 AM ET. Scheduled runs on busy nights can be delayed or dropped.
  - **Keep a local fallback.** `tools/bot_counties_local.sh` (`INTERVAL=60`)
    runs the bot counties on the Mac. It doesn't commit, so the next morning
    the repo diverges from the bot's commits. Run
    `git rebase --autostash origin/main`, and keep the bot's data, which is
    newer.
  - **The schedule is now removed** (manual "Run workflow" only). Add it
    back for the next election.
- **Run long loops from your own Terminal (or tmux/launchd), not from an
  agent session.** The fallback loop died when the agent session restarted,
  and Cuyahoga sat frozen at Early-only for about an hour before anyone
  noticed.
- **Stale feeds:** an itemized county whose own total is more than 1,000
  votes and more than 5% behind the SOS total is treated as if it had no
  feed (`common.timing.stale_feed`). It falls back to SOS toplines and the
  first-drop split, with a note. It caught Athens, Seneca, Van Wert, Hocking,
  Paulding and Cuyahoga.
- **The first-drop estimate works.** It splits pre-Election-Day from
  Election Day using the last SOS report with 0 precincts.
  - **Accuracy:** where a county's own split was known, it matched within
    about 13 votes (Clermont −13, Madison −12).
  - **Failure cases:** a county whose first report already includes
    precincts (Ashtabula, Belmont, Harrison, Morrow), and odd drops (Monroe
    looked wrong; Geauga, Wyandot and Darke had implausible mode splits).
  - **Timing:** the loop must be running before ~7:30 PM, or there's no
    0-precinct snapshot to read.
- **Our feed vs AP:** our county feeds were usually equal to or ahead of AP
  (9:33 PM: 57 equal, 23 ahead by 123k, 8 behind by 115k). The 8 behind
  were all stuck scrapers.
  - **AP's mode fields** covered only the counties where AP had a split (14
    to 17 for Eday/Early).
  - **Where AP lagged:** Richland, Darke and Tuscarawas, among others.
- **"Early" means all pre-Election-Day votes**, early in-person + mail
  (`early = evip + vbm`). In-person early is in-office absentee in most
  county labels.
- **Credentials:** the agent's shell has no GitHub token. Push from your own
  Terminal. The local loop asks for a token once and holds it in memory.

### 4. Projection lessons (the `projection` tab)

- **"Done" by closeness to expected Eday alone is too strict.** Statewide,
  Election Day turnout ran below the model. By about 10:15 PM, 57 counties
  had every precinct in, but only 15 reached 95% of expected Eday. The other
  40 kept "projecting" about 43k phantom votes, worth about −18k margin
  because they were red.
  - **Fix:** done = every precinct in **or** Eday ≥ cutoff (B2). Precinct
    counts are only trustworthy once they're complete.
  - **Watch out:** "done counties came in at 99.9% of expected Eday" is
    biased, because only counties that reach the cutoff get marked done.
    Calibrate on fully reported counties instead.
- **A county's first Eday batch is not representative.** Cuyahoga's first
  12.7k Eday votes (0 of 897 precincts) were 59.9% Brown 2-way against a
  prior of 69.8%. Applying that "so far" share to its ~299k remaining Eday
  understated the margin by about 35–40k. Treat a county under ~10% of
  expected Eday with caution.
- **A county with no votes at all is projected at zero.** That follows the
  no-imputation rule; Lucas (about +34k at the priors) sat outside the
  projection all night. Show any such county separately with its prior, so
  the omission is visible.
- **Calibration from fully reported counties, Nov 3, 2026** (vs the model's
  frozen priors):
  - Eday turnout came in at about 94.5% of expected; Early at about 100%.
  - **Eday 2-way ran about 3.0 pts below prior**, and **Early about 2.7–2.9
    pts above**. In-person early beat its prior by +4.7, mail by +1.5.
  - The two offset: in done counties, total 2-way landed within 0.01 pts of
    `expected_frozen_two_way`.
- **Expected votes may exclude late mail and provisionals.** We didn't
  confirm whether the model's expected counts include them. If not, the
  projection is the election-night count, and the canvass adds votes that
  usually lean Dem.
- **Third parties:** 4.7% statewide (Redpath 2.7, Levy 1.9). Redpath tracks
  partisanship closely (R² 0.77); Levy is flat apart from Wyandot (11.5%).

### 5. Analysis scripts from the night

All read the owner's sheet ("scarv E-night", `GSHEET_ID`) read-only and write
a PNG:

| Script | What it shows |
|---|---|
| `tools/_early_vs_prior.py` | Early 2-way actual vs `early_exp_two_way`, itemized vs first-drop, EVIP and VBM |
| `tools/_turnout_done.py` | Turnout vs expected in done counties, by mode, against Brown share |
| `tools/_plot_done_vs_prior.py` | Done counties: AP 2-way vs `expected_frozen_two_way` |
| `tools/_plot_third_party.py` | Third-party share vs Brown 2-way (AP) |
| `tools/_eday_drift.py <county...>` | A county's Eday margin batch by batch, from git history |
| `tools/_audit_projection.py`, `tools/_audit_validations.py` | Recompute the sheet tabs in Python and list mismatches |

### 6. Checklist for next cycle

1. **New election IDs and URLs:** rerun `tools/discover_enr.py` and the
   county survey. Update `counties.csv`, then `python -m tools.make_counties_md`.
2. **Retest the bot counties' endpoints:** Enhanced Voting election slugs
   (Cuyahoga, Summit, Montgomery, Greene, Pickaway, Hocking) and Franklin's
   XML.
3. **Re-add the Actions schedule** with new dates, keep the year guard
   current, and still plan on the local fallback.
4. **Freeze the model snapshots** in section 1, and confirm the mode priors
   cover all 88 counties.
5. **Fix the "done" rule** in `tools/sheet_projection.py` (precincts
   complete or cutoff) before the night, not during it.
6. **Do a dry run** the week before (`DRY_RUN=1 ONCE=1 tools/local_loop.sh`)
   plus one live push to a test sheet. Run every loop from your own
   Terminal.
7. **Install the tools:** `gh` CLI (to check and disable Actions runs) and
   `pytest` (the tests currently run by calling test functions directly).

<!-- COUNTY-SUMMARY:START -->

## County summary (largest expected vote first)

Generated by `python -m tools.make_counties_md`; details per county in [COUNTIES.md](COUNTIES.md).
Ordered by `exp_total_votes` from the DSCC election-night workbook's `county_raw` tab
(saved in `tools/expected_votes.csv`). "Split" means Senate votes by method on election night.

**Share of the expected statewide vote, by what we'll have:**

- **Split by method, scraper live or waiting for a link:** 60.8% (25 counties)
- **Maybe on election night (precinct or scanned PDF, likely, or unknown):** 7.6% (19 counties)
- **Gap until the official canvass (~Nov 17-24):** 10.6% (17 counties)
- **Gap with no split expected (totals only):** 21.0% (27 counties)

**Before vs on Election Day (the split that matters most) covers every county:** directly from the vote-type split for the 60.8% above, and as a **first-drop estimate** for the rest (`common/timing.py`): Ohio counties release absentee and early ballots before any precinct, so a county's last report with 0 precincts in is its pre-Election-Day vote. The estimate fails for a county whose first report already includes precincts, and it needs the local loop running before the first results (~7:30 PM). Mail vs in-person is a bonus where the county reports it (`has_mail_inperson_split`).

| # | County | Expected votes | % of state | Cumulative % | Split on election night | Before / on Election Day | Source (runs in) | Gap |
|---|---|---|---|---|---|---|---|---|
| 1 | Franklin | 487,197 | 10.5% | 10.5% | Yes | Direct | County-hosted ENR XML, Actions | Mail column (Absentee Ballots) is an inference |
| 2 | Cuyahoga | 473,712 | 10.2% | 20.7% | Yes | Direct | Enhanced Voting Excel export, Actions | Unassigned vote types: Post Election Day; Post VBM |
| 3 | Hamilton | 334,664 | 7.2% | 27.9% | Yes | Direct | Clarity detail XML, local loop | Early not split into in-person vs mail; no provisional column |
| 4 | Summit | 223,260 | 4.8% | 32.7% | Yes | Direct | Enhanced Voting JSON API, Actions | Unassigned vote types: Timely Abs |
| 5 | Montgomery | 203,312 | 4.4% | 37.1% | Yes | Direct | Enhanced Voting JSON API, Actions | Unassigned vote types: Absentee/Early Voting/Election Day Add-In |
| 6 | Lucas | 152,119 | 3.3% | 40.4% | Yes | Direct | SOS-hosted ENR XML, local loop | Mail column (Absentee Ballots) is an inference; no write-in line |
| 7 | Stark | 148,722 | 3.2% | 43.6% | Yes | Direct | SOS-hosted ENR XML, local loop | None |
| 8 | Butler | 144,349 | 3.1% | 46.7% | Yes | Direct | SOS-hosted ENR XML, local loop | None |
| 9 | Lorain | 129,115 | 2.8% | 49.5% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 10 | Delaware | 114,490 | 2.5% | 51.9% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 11 | Warren | 113,188 | 2.4% | 54.4% | Yes | Direct | SOS-hosted ENR XML, local loop | None |
| 12 | Lake | 104,462 | 2.3% | 56.6% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24. County-hosted site: the Nov 3 recheck is manual |
| 13 | Clermont | 92,894 | 2.0% | 58.6% | Yes | Direct | Results PDF, local loop | Election-night file name unknown; scraper picks it from the results page (until then it reads the zero report). Check the loop log for 'parsing the zero report' after 7:30 PM |
| 14 | Mahoning | 89,694 | 1.9% | 60.6% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes. County-hosted site: the Nov 3 recheck is manual |
| 15 | Medina | 87,360 | 1.9% | 62.4% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 16 | Trumbull | 78,133 | 1.7% | 64.1% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 17 | Licking | 75,053 | 1.6% | 65.7% | Yes | Direct | Results PDF, local loop | None |
| 18 | Greene | 73,017 | 1.6% | 67.3% | Yes | Direct | Enhanced Voting JSON API, Actions | None |
| 19 | Portage | 67,867 | 1.5% | 68.8% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 20 | Fairfield | 67,377 | 1.5% | 70.2% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 21 | Wood | 56,125 | 1.2% | 71.4% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes. County-hosted site: the Nov 3 recheck is manual |
| 22 | Clark | 49,627 | 1.1% | 72.5% | Yes | Direct | SOS-hosted ENR XML, local loop | Mail column (Absentee Ballots) is an inference |
| 23 | Miami | 47,017 | 1.0% | 73.5% | Yes | Direct | Results PDF, local loop | Column order not yet verified on real votes |
| 24 | Richland | 46,541 | 1.0% | 74.5% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 25 | Geauga | 46,030 | 1.0% | 75.5% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 26 | Wayne | 41,839 | 0.9% | 76.4% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 27 | Columbiana | 36,494 | 0.8% | 77.2% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 28 | Allen | 35,682 | 0.8% | 78.0% | Yes, once posted | Direct | Results PDF, local loop | Scraper waits for the election-night PDF link; Early not split into in-person vs mail |
| 29 | Ashtabula | 34,728 | 0.7% | 78.7% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 30 | Tuscarawas | 32,873 | 0.7% | 79.4% | Likely | Estimate (first drop) | Statewide totals only | No scraper yet; the 8:30/9:30 PM recheck builds one if the Nov 3 file is split |
| 31 | Erie | 31,888 | 0.7% | 80.1% | Yes | Direct | Results PDF, local loop | Early not split into in-person vs mail |
| 32 | Union | 31,637 | 0.7% | 80.8% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 33 | Hancock | 30,195 | 0.7% | 81.5% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 34 | Muskingum | 29,501 | 0.6% | 82.1% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 35 | Knox | 25,608 | 0.6% | 82.6% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3 |
| 36 | Ross | 25,576 | 0.6% | 83.2% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 37 | Washington | 24,812 | 0.5% | 83.7% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 38 | Belmont | 24,122 | 0.5% | 84.2% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 39 | Sandusky | 23,767 | 0.5% | 84.8% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24. County-hosted site: the Nov 3 recheck is manual |
| 40 | Jefferson | 23,706 | 0.5% | 85.3% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 41 | Pickaway | 23,345 | 0.5% | 85.8% | Yes | Direct | Enhanced Voting JSON API, Actions | None |
| 42 | Scioto | 23,328 | 0.5% | 86.3% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 43 | Marion | 21,414 | 0.5% | 86.7% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 44 | Ashland | 21,021 | 0.5% | 87.2% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 45 | Huron | 20,879 | 0.4% | 87.6% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 46 | Athens | 20,746 | 0.4% | 88.1% | Yes | Direct | Results PDF, local loop | None |
| 47 | Darke | 20,678 | 0.4% | 88.5% | Likely | Estimate (first drop) | Statewide totals only | No scraper yet; the 8:30/9:30 PM recheck builds one if the Nov 3 file is split |
| 48 | Lawrence | 20,430 | 0.4% | 89.0% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 49 | Seneca | 20,255 | 0.4% | 89.4% | Yes | Direct | Results PDF, local loop | None |
| 50 | Auglaize | 19,981 | 0.4% | 89.8% | Likely | Estimate (first drop) | Statewide totals only | No scraper yet; the 8:30/9:30 PM recheck builds one if the Nov 3 file is split |
| 51 | Ottawa | 19,963 | 0.4% | 90.3% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24. County-hosted site: the Nov 3 recheck is manual |
| 52 | Shelby | 19,690 | 0.4% | 90.7% | **In precinct PDF only** | Estimate (first drop) | Statewide totals only | Split only in the precinct PDF; summing parser not built, so totals only for now |
| 53 | Mercer | 18,896 | 0.4% | 91.1% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 54 | Logan | 18,343 | 0.4% | 91.5% | Likely | Estimate (first drop) | Statewide totals only | No scraper yet; the 8:30/9:30 PM recheck builds one if the Nov 3 file is split |
| 55 | Fulton | 17,987 | 0.4% | 91.9% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3 |
| 56 | Preble | 17,087 | 0.4% | 92.3% | Yes | Direct | Results PDF, local loop | Unassigned vote types: Absentee Late |
| 57 | Madison | 16,683 | 0.4% | 92.6% | Yes | Direct | Results PDF, local loop | None |
| 58 | Brown | 16,568 | 0.4% | 93.0% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 59 | Putnam | 16,273 | 0.4% | 93.3% | **In precinct PDF only** | Estimate (first drop) | Statewide totals only | Split only in the precinct PDF; summing parser not built, so totals only for now |
| 60 | Champaign | 16,025 | 0.3% | 93.7% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 61 | Crawford | 15,999 | 0.3% | 94.0% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes. County-hosted site: the Nov 3 recheck is manual |
| 62 | Clinton | 15,962 | 0.3% | 94.4% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 63 | Morrow | 15,290 | 0.3% | 94.7% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 64 | Defiance | 15,042 | 0.3% | 95.0% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 65 | Highland | 15,003 | 0.3% | 95.3% | **In precinct PDF only** | Estimate (first drop) | Statewide totals only | Split only in the precinct PDF; summing parser not built, so totals only for now |
| 66 | Williams | 14,547 | 0.3% | 95.6% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 67 | Guernsey | 13,127 | 0.3% | 95.9% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes. County-hosted site: the Nov 3 recheck is manual |
| 68 | Perry | 13,096 | 0.3% | 96.2% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3 |
| 69 | Coshocton | 12,913 | 0.3% | 96.5% | Likely | Estimate (first drop) | Statewide totals only | No scraper yet; the 8:30/9:30 PM recheck builds one if the Nov 3 file is split |
| 70 | Henry | 11,932 | 0.3% | 96.7% | **Unknown** | Estimate (first drop) | Statewide totals only | Nothing to check in advance; recheck on Nov 3. County-hosted site: the Nov 3 recheck is manual |
| 71 | Van Wert | 11,465 | 0.2% | 97.0% | Yes | Direct | Results PDF, local loop | None |
| 72 | Jackson | 10,983 | 0.2% | 97.2% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 73 | Carroll | 10,566 | 0.2% | 97.5% | Yes | Direct | SOS-hosted ENR XML, local loop | None |
| 74 | Hocking | 10,294 | 0.2% | 97.7% | Yes | Direct | Enhanced Voting JSON API, Actions | None |
| 75 | Gallia | 9,985 | 0.2% | 97.9% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 76 | Hardin | 9,959 | 0.2% | 98.1% | **In scanned PDF only** | Estimate (first drop) | Statewide totals only | Split is in a scanned (image) PDF; no OCR parser, so totals only unless read by hand |
| 77 | Adams | 9,878 | 0.2% | 98.3% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 78 | Fayette | 9,591 | 0.2% | 98.5% | **In scanned PDF only** | Estimate (first drop) | Statewide totals only | Split is in a scanned (image) PDF; no OCR parser, so totals only unless read by hand |
| 79 | Holmes | 9,367 | 0.2% | 98.7% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 80 | Pike | 9,325 | 0.2% | 98.9% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 81 | Wyandot | 8,768 | 0.2% | 99.1% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 82 | Meigs | 8,402 | 0.2% | 99.3% | **No** | Estimate (first drop) | Statewide totals only | No split published; totals only |
| 83 | Paulding | 7,382 | 0.2% | 99.5% | Yes | Direct | Results PDF, local loop | Early not split into in-person vs mail |
| 84 | Harrison | 5,397 | 0.1% | 99.6% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 85 | Morgan | 5,379 | 0.1% | 99.7% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 86 | Monroe | 5,267 | 0.1% | 99.8% | **No (likely)** | Estimate (first drop) | Statewide totals only | No past report split; totals only unless the Nov 3 format changes |
| 87 | Noble | 4,841 | 0.1% | 99.9% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |
| 88 | Vinton | 4,377 | 0.1% | 100.0% | **No (canvass only)** | Estimate (first drop) | Statewide totals only | Totals only on election night; split expected in the official canvass ~Nov 17-24 |

<!-- COUNTY-SUMMARY:END -->

## Where things are

| What | Where | Notes |
|---|---|---|
| Per-county registry (machine-readable) | `counties.csv` | One row per county: FIPS, BOE site, platform, feed URLs, status, `history_split` verdict and evidence. Source for COUNTIES.md |
| Per-county status (human-readable) | `COUNTIES.md`, and the County summary above | Generated: `python -m tools.make_counties_md` (rewrites COUNTIES.md and the README section between the `COUNTY-SUMMARY` markers) |
| Expected votes per county (ordering) | `tools/expected_votes.csv` | `exp_total_votes` copied from the DSCC election-night workbook's `county_raw` tab on 2026-11-01 |
| One county's scraper | `counties/<county>/scraper.py` | Reads the county's whole feed into `output/summary_wide_latest.csv` (git-ignored, local only). `python -m tools.save_senate <county>` (run by the workflow and the loop) then commits **only the U.S. Senate race** to `data/summary_wide.csv`, and refuses to overwrite it if the feed has no single Senate race. Nothing in git holds other races |
| Combined Senate results | `results/senate_by_method.csv`, `results/senate_by_method_wide.csv` | Built by `python -m common.senate` from every `counties/*/data/` file plus the statewide totals. The Actions bot rebuilds them on election night |
| Statewide county totals (all 88, no split) | `results/senate_statewide_by_county.csv` | `python -m common.ohio_statewide` (headed Chromium; local only, blocked in Actions) |
| **Before vs on Election Day, all 88 counties** | `results/senate_by_timing.csv` | `python -m common.timing` (each loop cycle). `timing_source`: `itemized` (direct), `first_drop` (estimate for totals-only counties), `none`. Method and caveats in the `common/timing.py` docstring |
| Statewide snapshot log (time series) | `results/statewide_snapshots.csv` | Appended by `common.timing` whenever a county's totals change; the first-drop estimate reads it. Committed by the loop; don't delete or rewrite it |
| Data checks (Brown and Husted) | `common/senate.py` (`REQUIRED`, `check_senate_rows`) | A county update is **refused, keeping the last good file**, if Brown or Husted is missing or either one's vote types don't add up to their total. The statewide file must have Brown and Husted for all 88 counties. Levy, Redpath and write-in mismatches only warn. County-feed vs statewide differences are listed Brown/Husted first |
| Vote-label → method mapping | `common/senate.py` (`METHOD_MAP`, `EV_METHOD_MAP`) and the Buckets column of COUNTIES.md | Assumptions and unmapped labels are listed per county in COUNTIES.md |
| Shared parsers | `common/` | `ohio_enr.py` (Ohio ENR XML/CSV), `enhanced_voting.py`, `clarity.py`, `pdf_results.py` (PDF layouts), `sos_browser.py` (reads SOS files through a real Chrome window), `ohio_statewide.py` |
| Research outputs | `tools/*.json` | `survey60_verdicts.json` and `past_reports.json` (past-report checks, with document URLs and excerpts), `county_survey.json` (site crawl), `enr_discovery.json` (SOS ENR election IDs), `clarity_probe.json` |
| Research and election-night tools | `tools/*.py`, `tools/*.sh` | `local_loop.sh` (election-night loop), `sos_chrome.sh`, `recheck_zero_reports.py`, `make_pdf_scraper.py`, `make_sos_scrapers.py`, `discover_enr.py`, `survey_counties.py`, `past_reports.py`, `build_method_workbook.py`, `make_counties_md.py` |
| GitHub Actions workflow | `.github/workflows/election-night.yml` | Scrapes the 6 counties reachable from Actions and rebuilds `results/`. Ran every 5 min on election night 2026; the schedule is now removed (manual "Run workflow" only). See Lessons |
| Tests | `tests/` | `python -c "import tests.test_build_method_workbook as t; t.test_buckets()"` (pytest not required) |

**Not in git, on purpose:**

| What | Where | Why |
|---|---|---|
| Vote-method workbook for the Google Sheet (`OH_Senate_2026_vote_method.xlsx` + `votes_by_timing.csv`, `votes_by_method.csv`, `votes_long.csv`, `sources.csv`) | `../exports/` next to the clone on the loop machine | Rebuilt every loop cycle by `python -m tools.build_method_workbook ../exports`; anyone can rebuild it from the repo. Kept separate from the AP-based county aggregator; joins on `county_fips` |
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
Mac, which commits and pushes them every 5 minutes. So do Hamilton and
Clermont: their own hosts serve plain HTTP to a desktop, but Hamilton's
(CloudFront) gave GitHub's runner an empty file on the 2026-11-02 test run.
Counties on other hosts (Cuyahoga, Franklin, Montgomery, Summit, Pickaway,
Hocking) run in Actions; all six passed the manual run of 2026-11-02.

**The local loop runs its county scrapers only while the SOS Chrome window is
open** (it checks the Chrome debugging port first). If that window is closed,
Hamilton and Clermont stop too, even though they don't use it.

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
| 6:00 PM | Actions schedule starts (every 5 min) | Cuyahoga, Franklin, Montgomery, Summit, Pickaway and Hocking scraped in Actions (Hamilton runs in the local loop) |
| **7:00 PM: the one command** | `tools/election_night.sh` (test first with `tools/election_night.sh --test`) | Opens the scrapers2026 Chrome window in the background (or reuses it), checks the 3 SOS sites for a "Verify you are human" box (if one shows, that tab comes to the front with a notification; click it and it carries on), then starts the loop below with the Google Sheet set. Asks for your GitHub token once. Leave the Chrome window open all night; minimize it if you like |
| 7:00 PM (what the command runs) | `tools/sos_chrome.sh`, `python -m tools.preflight`, then the loop | Same as running the three steps by hand |
| 7:00 PM, **before the first results at ~7:30** | `GSHEET_ID=1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs tools/local_loop.sh` (enter token once; the `GSHEET_ID` part updates the owner's "scarv E-night" sheet, `methods` tab, every cycle) | Every 5 min: SOS ENR + PDF counties + statewide totals + timing snapshot, commit, push. Allen logs "not posted yet" until its link appears. **It must be running before the first absentee release**: the before/on-Election-Day estimate for totals-only counties reads the statewide snapshots taken while they have 0 precincts in. A county missed in that window shows `timing_source = none` |
| ~8:30 PM, after the first absentee uploads | In a second Terminal tab: `.venv/bin/python -m tools.recheck_zero_reports --make-scrapers` | Lists every still-unknown SOS-hosted county as no_file / total_only / SPLIT, and writes scrapers for the SPLIT ones (the loop picks them up next cycle). Takes ~5 min |
| ~9:30 PM | Run the recheck again, then commit the new scraper folders: `git add counties/ && git commit -m "Election-night recheck: new counties" && git push origin main` (or let the loop push on its next commit) | Catches counties that post later |
| Any time | Spot-check `results/senate_by_method_wide.csv` on GitHub | `source` column: `county_feed` (by method) or `sos_statewide` (totals only) |
| Every loop cycle (automatic) | `tools/local_loop.sh` step 4 runs `tools.build_method_workbook ../exports` | Rebuilds the standalone vote-method sheet (`OH_Senate_2026_vote_method.xlsx` + one CSV per tab: votes_by_method, votes_long, sources) after pulling the bot's latest. Re-import into the Google Sheet when you want to update it. `fetched_at` shows when each county's numbers were fetched. Separate from the AP aggregator; joins on `county_fips`. Run it by hand any time with the same command |
| 8:00 AM Nov 4 | Loop and schedule stop on their own | |

The recheck lists counties whose BOE site isn't SOS-hosted for a manual
look (their election-night address isn't predictable): Ottawa, Sandusky,
Crawford, Guernsey, Hancock, Henry, Mercer, Morrow, Union, Williams,
Delaware, Lake, Lorain, Mahoning, Portage, Trumbull, Wayne, Wood.
(Clermont, also county-hosted, now has its own scraper that finds its
election-night PDF on its results page.)
The most promising are **Lake and Ottawa**, whose official
reports split votes. If one posts a split PDF, add it with
`python -m tools.make_pdf_scraper "<County>" positional "<columns>"`, then
edit `URL`/`PAGE` in the generated `scraper.py` to the county's link.

If something breaks:
- **A browser window pops up every cycle**: the SOS Chrome window isn't open, so the statewide step is launching its own temporary Chromium (the log says so). Run `tools/sos_chrome.sh`.
- **"SOS Chrome window not open"** in the loop log: rerun `tools/sos_chrome.sh`.
- **"BLOCKED <site>: Cloudflare check"** (plus a macOS notification): click "Verify you are human" in the named tab of the scrapers2026 Chrome window. Only that site's counties are skipped meanwhile; the next cycle retries them.
- **HTTP 429**: the loop backs off on its own. Don't restart it.
- **A county's URL changes**: fix `URL` in `counties/<county>/scraper.py` and push. The others keep running.
- **The loop dies**: rerun `tools/local_loop.sh`. It pulls first, then carries on.

See REPORT.md.

## Google Sheet updates (optional)

Each loop cycle can copy `county_results.csv` into one tab of **your own**
Google Sheet (`tools/push_sheet.py`). It replaces only that tab, creating it
if needed, and refuses the AP aggregator's production sheet. Pull the AP
data into your sheet read-only with `IMPORTRANGE` instead.

One-time setup (~15 min):
1. [Google Cloud console](https://console.cloud.google.com/): create a project, then enable the **Google Sheets API** (APIs & Services → Library).
2. IAM & Admin → Service Accounts → **Create service account** (no roles needed) → its **Keys** tab → Add key → JSON. A key file downloads.
3. Move it out of Downloads and lock it down:
   ```bash
   mkdir -p ~/.config/scrapers2026 && mv ~/Downloads/<key>.json ~/.config/scrapers2026/google-sa.json && chmod 600 ~/.config/scrapers2026/google-sa.json
   ```
4. In your Google Sheet: **Share** → paste the service account's email (`client_email` in the key file, `...@...iam.gserviceaccount.com`) → **Editor**. If your Google Workspace blocks sharing outside the organization, create the sheet in an account that allows it.
5. Test, using the ID from the sheet's URL (`docs.google.com/spreadsheets/d/<ID>/edit`):
   ```bash
   GSHEET_ID=<ID> .venv/bin/python -m tools.push_sheet --check   # access test, writes nothing
   GSHEET_ID=<ID> .venv/bin/python -m tools.push_sheet           # one real push
   ```

Election night: start the loop with `GSHEET_ID=<ID> tools/local_loop.sh`
(`GSHEET_TAB=<name>` to use a tab other than `methods`). A failed push only
logs a warning; the next cycle retries.

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
`COUNTIES` setting. On election night 2026 it ran every 5 minutes from 6 PM ET
Nov 3 to 8 AM ET Nov 4; that schedule has been removed, so it now runs only
from "Run workflow". Restore the `schedule:` block (the old cron lines are in
the file's header comment) for the next election, and don't rely on it alone
(see Lessons). After scraping it rebuilds `results/`; when anything changes it commits each
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
