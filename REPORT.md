# Status report (interim, 2026-11-01)

## Summary

- **By vote method, 8 counties:**
  - Cuyahoga and Franklin, from county-hosted feeds over plain HTTP (these
    also run in Actions).
  - Butler, Carroll, Clark, Lucas, Stark and Warren, from their SOS ENR
    summary XML, read through a Chrome window the owner opens
    (`tools/sos_chrome.sh`, `common/sos_browser.py`).
- **Totals only, no method split: the other 80 counties,** from the SOS
  statewide site (`common/ohio_statewide.py`). A scan of all 86 non-Cuyahoga,
  non-Franklin counties on the SOS ENR (`tools/discover_enr.py`, results in
  `tools/enr_discovery.json`) found no Nov 3 file for them. Those that were
  spot-checked (Adams, Allen) publish election-night results as PDFs with
  totals only.

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
