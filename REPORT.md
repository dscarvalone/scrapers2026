# Status report (interim, 2026-11-01)

## Summary

Two counties, Cuyahoga and Franklin, work live end to end and are scheduled
for election night. They are Ohio's two largest counties. The rest of the plan
is blocked: the Ohio Secretary of State's hosts, including the shared ENR
results feed most counties use, serve a Cloudflare JavaScript challenge to
datacenter IPs. Our egress and GitHub Actions runners are both datacenter
IPs. The project rules forbid bypassing blocks, so no attempt was made to
solve the challenge.

## What is blocked, and how it was confirmed

Every one of these returned HTTP 403 with a Cloudflare "security check /
enable JavaScript and cookies" page on 2026-11-01, including the site roots:

- liveresults.boe.ohio.gov (the shared ENR feed, used by Warren and Butler)
- liveresults.ohiosos.gov, www.ohiosos.gov
- www.boe.ohio.gov (SOS-hosted BOE sites, e.g. Summit)
- votehamiltoncountyohio.gov (Hamilton's own site, `cf-mitigated: challenge`)

The challenge is IP-based. Requests came from an AWS IP (AS16509). From a
residential connection the feed may load normally; that hasn't been tested.
The block page asks visitors to contact the SOS office (1-877-767-6446) with
the IP and reference ID to request access.

Also checked: livevoterturnout.com, the ENR vendor's own host, is reachable,
but it only has Butler's 2020 elections. Counties have since moved to the
SOS host, so it is not a mirror for Nov 2026.

## Counties

| Status | Counties | Source |
|---|---|---|
| Working | Cuyahoga | Enhanced Voting xlsx |
| Working | Franklin | County-hosted ENR (liveresults.franklincountyohio.gov), election ID 4 |
| Blocked | Warren, Butler, Summit, Hamilton | SOS ENR / SOS-hosted or Cloudflare-protected sites |
| Reachable, no live feed found | Lake, Clermont | Post-election PDF/HTM only |
| Not yet surveyed | 80 others | See counties.csv |

Full per-county registry: `counties.csv` (88 rows).

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
