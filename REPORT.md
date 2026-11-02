# Status report (interim, 2026-11-01)

## Summary

- **By vote method, 21 counties now, 22 once Allen posts.** See the
  88-county table under "Survey of the remaining 60 counties" for the full
  breakdown. 7 run in Actions over plain HTTP; 14 (plus Allen) run in the
  local loop through the owner's Chrome window.
- **Totals only, no method split: the other 67 counties,** from the SOS
  statewide site (`common/ohio_statewide.py`). 9 of them are confirmed totals
  only; 4 have a split we don't scrape yet; the rest are unknown until
  election night.

The SOS hosts serve a Cloudflare check to every non-browser client, from
datacenter and residential IPs alike, and to headless browsers. The owner
waived the no-bypass rule for a real browser. See "Browser access" below.

## What is blocked, and how it was confirmed

Every one of these returned HTTP 403 with a Cloudflare "security check /
enable JavaScript and cookies" page on 2026-11-01, including the site roots:

- liveresults.boe.ohio.gov (the shared ENR feed, used by Warren and Butler)
- liveresults.ohiosos.gov, www.ohiosos.gov
- www.boe.ohio.gov (SOS-hosted BOE sites, e.g. Summit)
- votehamiltoncountyohio.gov (Hamilton's own site, `cf-mitigated: challenge`)

The challenge is NOT only for datacenter IPs. It was confirmed from an AWS IP
(AS16509) and again from a residential Charter connection (AS12271), where
`curl -sI` on Warren's summary XML also returned 403 from Cloudflare. It
applies to any non-browser client. Scripted access is not possible from
GitHub Actions or from a local machine.
The block page asks visitors to contact the SOS office (1-877-767-6446) with
the IP and reference ID to request access.

Also checked: livevoterturnout.com, the ENR vendor's own host, is reachable,
but it only has Butler's 2020 elections. Counties have since moved to the
SOS host, so it is not a mirror for Nov 2026.

## Counties

Working: Cuyahoga (Enhanced Voting xlsx) and Franklin (county-hosted ENR,
election ID 4). All 88 counties are classified in the canonical access list
below. A DNS check of 8 common hostname patterns across all 88 also found
no other county-hosted ENR besides Franklin.

## Canonical access list (all 88 counties, surveyed 2026-11-01)

Each county's official BOE website was taken from the SOS County Boards of
Elections Directory (saved by the owner from
https://www.ohiosos.gov/directories/county-boards-of-elections). Every
county-owned site was then fetched by script, crawling up to 8 election and
results pages, to see where results are published. Per-county detail is in
`counties.csv` (columns access_class, boe_url, boe_host).

| Class | Meaning | Count | Counties |
|---|---|---|---|
| A | Live results on a county-hosted feed, scriptable today | 2 | Cuyahoga, Franklin |
| B | County site reachable; it links election-night results to the SOS ENR (blocked to scripts) | 3 | Butler, Stark, Warren |
| C | County site reachable; no live-results link found, only PDF/CSV results posted after the fact. Election-night source unknown, probably SOS ENR | 18 | Clermont, Crawford, Delaware, Guernsey, Hancock, Henry, Lake, Lorain, Mahoning, Mercer, Morrow, Ottawa, Sandusky, Trumbull, Union, Wayne, Williams, Wood |
| D | County-owned BOE site itself behind a Cloudflare challenge | 3 | Hamilton, Lucas, Portage |
| E | BOE site hosted by SOS (boe.ohio.gov path or subdomain, or redirects there); blocked to scripts | 62 | Adams, Allen, Ashland, Ashtabula, Athens, Auglaize, Belmont, Brown, Carroll, Champaign, Clark, Clinton, Columbiana, Coshocton, Darke, Defiance, Erie, Fairfield, Fayette, Fulton, Gallia, Geauga, Greene, Hardin, Harrison, Highland, Hocking, Holmes, Huron, Jackson, Jefferson, Knox, Lawrence, Licking, Logan, Madison, Marion, Medina, Meigs, Miami, Monroe, Montgomery, Morgan, Muskingum, Noble, Paulding, Perry, Pickaway, Pike, Preble, Putnam, Richland, Ross, Scioto, Seneca, Shelby, Summit, Tuscarawas, Van Wert, Vinton, Washington, Wyandot |

"With BOE" vs "without": only class A counties publish election-night
results somewhere other than the SOS platform that a script can reach. For
B, C and E the SOS platform is the only identified live source. For D the
county's own site can't be read by script either.

Limits: class C is "no live link found on the site today". A county could
add a non-SOS link on election night. Class E sites were not opened
individually (SOS-hosted, so script-blocked); that their live results are on
the SOS ENR is presumed, not verified per county.

### Survey of the remaining 60 counties, and new scrapers (2026-11-01 night)

Six parallel agents ran `tools/survey_counties.py` and `tools/past_reports.py`
over the 60 counties not yet covered (10 each, 6 s pacing through the
shared Chrome window) and wrote per-county verdicts. Merged:
`tools/survey60_verdicts.json`. The "yes" findings were then checked by
hand on the Senate block itself, and scrapers built:

- **Enhanced Voting (plain HTTP, run in Actions):** Pickaway (Election Day,
  In Office Absentee, Mail Absentee, Provisional) and Hocking (Election Day,
  Early Voting, Absentee, Provisional).
- **Nov 3 results PDF already posted with the split (local loop, Chrome
  window):** Van Wert, Madison, Preble, Erie, Paulding, Athens.
- **Allen:** election-night PDF link not posted yet. The scraper watches
  Allen's results page and reports "not posted yet" until it appears.
- **Split exists but not scraped:** Putnam, Shelby, Highland (only their
  per-precinct PDFs have the split; the summary is TOTAL only); Jackson
  (scanned PDF, no text layer).

**Position-based PDF parsing, and a Licking fix.** In ES&S/Electionware
reports, multi-line column headers come out of plain text extraction in an
order that differs between counties running the same software. So
`common/pdf_results.parse_positional` assigns each number to the header
printed above it on the page (pdfplumber word coordinates). Checked on May
2026 reports with real votes for Licking, Madison, Preble, Erie, Paulding
and Athens, and on Allen's Nov 2025 report. **It showed the earlier
Licking scraper had Absentee Mail and Absentee Office swapped** (Mail and
Early In-Person). The sum check couldn't catch that, since a swap still sums
correctly. Licking now uses the positional parser. Miami (Dominion layout)
still uses its own parser, with the order taken from the printed header.

**All 88 counties, as of 2026-11-01 night:**

| Status | # | Counties |
|---|---|---|
| Itemized by method, scraper working | 21 | Cuyahoga, Franklin, Montgomery, Summit, Hamilton, Pickaway, Hocking (Actions); Butler, Carroll, Clark, Lucas, Stark, Warren, Licking, Miami, Erie, Madison, Preble, Paulding, Athens, Van Wert (local loop) |
| Itemized, link appears on election night | 1 | Allen |
| Split exists, not scraped | 4 | Putnam, Shelby, Highland (precinct PDFs), Jackson (scan) |
| Confirmed totals only | 9 | Fairfield, Richland, Ashland, Holmes, Gallia, Meigs, Adams, Brown, Defiance |
| Unknown, likely yes (past election-night report split) | 5 | Logan, Darke, Tuscarawas, Auglaize, Coshocton |
| Unknown, possible (past official reports split) | 19 | Clermont, Lake, Columbiana, Champaign, Morgan, Sandusky, Belmont, Geauga, Ottawa, Noble, Ashtabula, Clinton, Fayette, Hardin, Huron, Vinton, Ross, Pike, Seneca |
| Unknown, leaning no / no evidence | 29 | Greene, Wayne, Medina, Trumbull, Delaware, Lorain, Mahoning, Portage, Wood, Wyandot, Crawford, Jefferson, Scioto, Hancock, Perry, Knox, Mercer, Henry, Williams, Morrow, Guernsey, Lawrence, Monroe, Union, Fulton, Harrison, Marion, Muskingum, Washington |

Many SOS-hosted counties publish election-night results at
`www.boe.ohio.gov/<county>/c/elecres/20261103results.pdf`, the same address
where the "past official" reports were found (the file is overwritten with
the canvass later). So several "possible" counties may well post a split on
election night. Rerunning the zero-report check on Nov 3 evening would
settle them.

### Past election reports for the 15 non-itemized large counties (2026-11-01)

Zero reports alone are weak evidence, so `tools/past_reports.py` checked
what each county actually published for the Nov 4, 2025 and May 5, 2026
elections. It looks inside the first contest block for vote-type columns.
Raw output: `tools/past_reports.json`.

| County | Past reports show | Election-night split likely? |
|---|---|---|
| **Allen** | Nov 2025 **Unofficial** (election-night) PDF: TOTAL, Election Day, Absentee, Provisional (e.g. 353 = 302 + 51 + 0) | **Yes.** Posted as a Dropbox link on its BOE site; the Nov 3 link won't exist until it's posted |
| **Clermont** | Official "Summary Group Detail" (Election Day, Absentee In-Person, Absentee Mail, Provisional) for 2024-2026. Also an election-night-timed CSV (Nov 4 2025, 6:15 AM) that couldn't be fetched (Cloudflare, and a cross-site redirect in Chrome) | Possible; unresolved |
| **Lake** | Official "Group Detail" (Election Day, ED Paper, ABS By Mail, Early Vote, Provisional) for 2024-2026 | Official canvass only seen; election night unknown |
| Fairfield, Richland | Total-only in every past report (Nov 2025, May 2026, May 2025) | **No.** Confident |
| Greene | May 2026 results: total only | Probably no |
| Medina | Nov 3 zero report total only; past PDFs had no text layer | Inconclusive |
| Delaware | Past summaries are scans; "Key Canvass" text files didn't parse as split | Inconclusive |
| Wayne | Official May 2026 and zero reports: total only (Hart layout) | Probably no |
| Columbiana | Mixed: two official summaries split (Election Day, Absentee In Office, ...), the May 2026 official is total only | Possible; unclear |
| Trumbull, Lorain, Mahoning, Portage, Wood | Crawler found no past result documents | Inconclusive |

So "totals only" is only confirmed for Fairfield and Richland (and probably
Greene and Wayne). The rest are unknown.

### Hamilton via Clarity (2026-11-01, link from the owner)

Hamilton publishes on a Clarity/Scytl site,
results.votehamiltoncountyohio.gov/OH/Hamilton/127473/, which
`tools/survey_counties.py` missed (its live-results pattern didn't match a
`results.<county>` host). `common/clarity.py` reads `current_ver.txt`, then
`<ver>/reports/detailxml.zip`. That's plain HTTP, so it runs in Actions.
Hamilton has only two vote types:
- "Election" maps to Election Day.
- "Early" maps to the combined "Absentee (early in-person + mail)" bucket,
  because the site doesn't say whether it is mail, in-person or both.

There is no separate provisional column. The three named write-in
candidates ("(W)") are summed into Write-in.

`tools/probe_clarity.py` then checked every non-itemized county for a
Clarity site: Clarity-hosted (`results.enr.clarityelections.com/OH/<County>/`)
and `results.<county domain>`. The only other account is **Fulton**, and its
election list is empty for now ("Elections not available"), so it's worth
rechecking on Nov 3. Results: `tools/clarity_probe.json`.

### Survey of the 20 largest remaining counties (2026-11-01 evening)

`tools/survey_counties.py` visited each county's official BOE site, followed
its results pages, and opened every Nov 3, 2026 document or live-results
link it found. Raw output: `tools/county_survey.json`. Four more counties
have a vote-method split and now have scrapers:

| County | Source | Vote groups | Runs in |
|---|---|---|---|
| Montgomery | Enhanced Voting public JSON | Absentee, Early Voting, Election Day, Provisional (+ 3 "Add-In" groups) | Actions |
| Summit | Enhanced Voting public JSON | Abs Mail, Polls, Abs Walk-in, Provisional, Timely Abs | Actions |
| Licking | Election-night PDF (ES&S Electionware) | Election Day, Absentee Office, Absentee Mail, Provisional | local loop |
| Miami | Election-night PDF (Dominion) | AB, ED, EV, PR | local loop |

- Licking's column order was verified on its May 2026 report, where the
  columns sum to TOTAL for every race. Miami's order is taken from the
  printed header. Its May PDF has no text layer, so that's not yet
  confirmed on real votes.
- Enhanced Voting's "Absentee" sits next to a separate "Early Voting" group,
  so it is mapped to Mail, unlike the ENR CSV's combined "Absentee".
  Add-In and Timely groups are left unmapped.
- **Totals only** (their Nov 3 zero-report PDF has just a TOTAL column):
  Fairfield, Richland, Medina, Trumbull.
- **Nothing found yet** (no Nov 3 results document or live link on the
  site; may appear on election night): Lorain, Lake, Mahoning,
  Delaware, Clermont, Greene, Portage, Wood, Allen, Wayne, Columbiana.
  Worth rechecking on Nov 3.
- The other 60 smaller counties have not been surveyed this way.

### SOS ENR via the owner's Chrome window (added 2026-11-01, later the same day)

Supersedes the "not reachable" conclusion in the next section. The summary
XML loads in an ordinary Chrome window that a person opens. Playwright-
launched browsers are refused. So `common/sos_browser.py` doesn't launch
anything. It connects to a Chrome window the owner starts with
`tools/sos_chrome.sh`: a dedicated empty profile, with a debugging port on
127.0.0.1 only. It then makes same-origin `fetch()` calls from that window.
It never interacts with a challenge; if one appears it stops and asks a
person.

- **Rate limit:** the host returned HTTP 429 after about 30 requests at
  1 per second. Requests are now paced at one per 3 s, with a 60/120/240 s
  backoff on 429.
- **Discovery:** each county's newest ENR file is found with a coarse probe
  (IDs 40, 32, 24, ...) and then stepped up. A file counts only if it is a
  2026 general election with Brown and Husted in the same U.S. Senate race.
  Six counties have one:

| County | ENR ID | Vote types in feed | CSV |
|---|---|---|---|
| Butler | 24 | Early Voting, Absentee Voting, Election Day, Provisional | yes |
| Carroll | 23 | Early Voting, Mail Ballots, Election Day, Provisional | no |
| Clark | 20 | Early Voting, Absentee Ballots, Election Day, Provisional | yes |
| Lucas | 23 | Early Voting, Absentee Ballots, Election Day, Provisional | no |
| Stark | 14 | Early In Person, Vote by Mail, Election Day, Provisional | yes |
| Warren | 18 | Early Voting, Mail Ballots, Election Day, Provisional | yes |

  Hamilton and Lake have ENR folders, but only for older elections (newest:
  2025 and 2022). Summit's folder stops at 2024; one older Summit file uses a
  different schema (PollsVotes, ABSWalkinVotes, ABSMailVotes,
  TimelyABSVotes), which the parser now accepts. Summit's "Timely Absentee"
  is left unmapped.
- **Mapping:** "Absentee Voting" / "Absentee Ballots" are mapped to Mail
  because Early Voting is its own column. On Butler's ENR page this is
  stated directly: its hidden setting `hdnMailVote` has the value
  "Absentee Voting".
- **Lucas** publishes no Write-in line in its Senate race, so its Write-in
  row is missing from the combined file (439 rows, not 440).
- **Connection drops:** the debugging connection dropped about every 40
  minutes during the long discovery scan. The fetcher reconnects
  automatically. A drop in the middle of a request can still fail that one
  cycle; the next cycle retries.
- **Election night:** `tools/local_loop.sh` runs these six
  (`tools.run_sos_counties`) and the statewide fetch every 5 minutes, and
  commits only the files it owns. Six counties at 3 s each is about 20 s
  per cycle.

### Browser access (owner waived the no-bypass rule on 2026-11-01)

The owner waived the no-bypass rule for this. Self-imposed limits: a real,
unmodified Chromium only; no stealth plugins, fingerprint spoofing or CAPTCHA
solving; no more than 1 request per second per host. Findings with Playwright
1.64.1 on a desktop (Charter residential IP), 2026-11-01:

| What | Headless Chromium | Headed Chromium |
|---|---|---|
| SOS ENR results page (`ENR/<county>ohenr/<id>/en/Index_<id>.html`) | Blocked ("Website Maintenance" page) | Loads (real page) |
| SOS ENR summary XML/CSV (has the vote-method split) | Blocked | **Cloudflare Turnstile CAPTCHA**; doesn't clear. Stopped there. |
| Statewide site, Ohio Decides (liveresults.ohiosos.gov) and its JSON API | Blocked | Loads; API returns live JSON |

So with a headed browser:

- **The vote-method split is not reachable** for the 86 counties without a
  county-hosted feed. It exists only in each county's summary XML/CSV, which
  is behind Turnstile. The county results page itself shows totals only, and
  its vote-type "details" table is disabled in the HTML. (The page's own
  details view would load the same Turnstile-protected XML.)
- **County totals for all 88 counties are reachable** from Ohio Decides.
  `common/ohio_statewide.py` loads the site and makes the same API call the
  page makes for U.S. Senator, county level. That's two requests per run.
  Output: `results/senate_statewide_by_county.csv`. `common/senate.py` uses it
  to fill every county that has no county scraper, putting the votes in a
  "Not split by method" column (`source` = sos_statewide). Where a county feed
  exists it's cross-checked against the statewide total, with a warning on
  mismatch (expected briefly on election night while the sites update).

The statewide site lists three certified write-in candidates individually
(Stephen Faris, Anthony Holliman, Timothy Telymonde). They are summed into
"Write-in" to match county feeds; the breakdown is kept in `write_in_detail`.

Butler's SOS ENR election ID for Nov 3, 2026 is 24 (confirmed: the page says
November 3, 2026 and lists the Senate race). Warren's ID 18 returns 404, so
it's not the current election.

**Where it runs: the owner's Mac, not GitHub Actions.** A manual workflow
run on 2026-11-01 confirmed that the statewide site blocks GitHub's runners
even with a headed browser under xvfb (stuck on "Just a moment..."). From the
owner's Mac it works in about 5 seconds. So:

- `tools/local_loop.sh` (formerly statewide_loop.sh) runs on the Mac on election night. Every 5
  minutes it fetches the county totals and, if they changed, commits and
  pushes only `results/senate_statewide_by_county.csv`, pulling with rebase
  first. It asks for a GitHub token once at startup and holds it only in
  memory. It keeps the Mac awake with `caffeinate` and stops at 8 AM ET Nov 4.
- The Actions workflow no longer tries the statewide site. Its combine step
  reads the committed statewide file, so every bot run's
  `results/senate_by_method_wide.csv` includes all 88 counties.

Tested: a dry run against the live site, and the commit/rebase/push path
against a local copy of the repo, including a bot commit landing in between
and a no-change cycle that commits nothing. Not yet tested: pushing to
GitHub itself.

If the Mac is off or the loop stops, the 86 statewide-filled counties keep
their last pushed totals (the `source_generated_at` timestamp shows how
old they are).

## Vote-method mapping

- Franklin "Absentee Ballots" is mapped to **Mail**. This is an ASSUMPTION:
  Franklin reports "Early Voting" separately, so "Absentee Ballots" should be
  the mailed ballots. It is not from a county definition.
- Cuyahoga "Post Election Day" and "Post VBM" are left unmapped (passed through
  as-is), pending the county's definitions.
- Counties on the ENR CSV fallback would report a combined "Absentee" (early
  in-person + mail). That bucket is kept separate rather than split.

## Code changes in this round

- `common/ohio_enr.py`: vote-method columns are detected from each feed, not
  hard-coded, so both the Warren/Butler sample schema and Franklin's live
  schema parse. The candidate total is whichever of `<Votes>`/`<TotalVotes>`
  matches the method sum. Optional CSV columns no longer crash the parser. A
  new `expect_year` guard catches a stale election ID.
- `common/senate.py`: strips the party prefix Franklin puts on names
  ("Dem Sherrod Brown"), maps "Absentee Ballots", and fixes the county display
  name for underscored folders (van_wert -> Van Wert).
- Franklin scraper added. Workflow COUNTIES = cuyahoga franklin (Warren and
  Butler removed because they'd fail every run), with a 1s pause between
  counties.

Verified: both scrapers run live with "Vote-type sums match totals". Franklin's
CSV fallback also parses. Franklin's May 2026 feed (390 rows with real votes)
sums correctly. A synthetic file in the Warren-sample schema still parses as
before. The combiner produces 10 rows (2 counties x 5 candidates). The GitHub
Actions workflow has not been run.

## Open decisions for the owner

1. Test the SOS feed from a residential connection. If it loads, ENR discovery
   and election-night scraping could run from a local machine instead of
   Actions.
2. Or ask the SOS office to allowlist the scraper or provide a data feed.
3. Survey the remaining counties' own sites (needs a person or an interactive
   browser; scripted search engines CAPTCHA or return junk).
