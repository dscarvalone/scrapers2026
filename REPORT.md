# Status report (interim, 2026-11-01)

## Summary

Two counties, Cuyahoga and Franklin, work live end to end and are scheduled
for election night. They are Ohio's two largest counties. The rest of the plan
is blocked: the Ohio Secretary of State's hosts, including the shared ENR
results feed most counties use, serve a Cloudflare JavaScript challenge to
datacenter IPs. Our egress and GitHub Actions runners are both datacenter
IPs. The owner later waived the no-bypass rule. A real browser does get
through, but no browser-based scraper exists yet (see "Browser access" below).

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

### Browser access (owner waived the no-bypass rule on 2026-11-01)

A real browser (the Kiro dashboard browser panel) gets through the Cloudflare
check: liveresults.boe.ohio.gov returned genuine pages and genuine 404s, not
the block page. So the SOS ENR is reachable by browser automation. It was not
turned into a scraper here because:
- the dashboard panel can't read XML content, and
- the local `playwright-cli` Chromium crashes on launch in this sandbox.

A Playwright-based fetcher for the SOS ENR summary XML is the remaining path
to classes B, C and E. It would need testing from wherever it will run on
election night. Cloudflare often treats headless browsers on datacenter
IPs, such as GitHub Actions, more strictly than a desktop browser.

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
