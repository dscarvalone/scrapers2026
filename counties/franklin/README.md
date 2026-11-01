# Franklin County, OH

**Source:** the county's own copy of the Ohio ENR software (not the
SOS-hosted liveresults.boe.ohio.gov, which blocks automated clients).

- Results page: https://liveresults.franklincountyohio.gov/enr/franklinohenr/4/en/index_4.html
- Scraper tries, in order:
  1. `https://liveresults.franklincountyohio.gov/enr/franklinohenr/4/summary_4.xml`
  2. `https://liveresults.franklincountyohio.gov/enr/franklinohenr/4/summary_4.csv`

Paths are lowercase (`/enr/`); the `/ENR/` form 301-redirects.

**Election ID 4** is the Nov 3, 2026 general: the feed was generated
2026-10-26 and has `For U.S. Senator (UTE 1-3-29)` with all five candidates
and 889 precincts. IDs 1-3 are earlier 2026 elections, and ID 5 is 404.
The county's vote.franklincountyohio.gov/elections page still links ID 1,
so the ID is pinned in `scraper.py` instead of read from that page. Both
sources were checked live on 2026-11-01.

## Vote methods

Franklin's feed has four vote-type columns, which sum exactly to each
candidate's total (checked on the May 2026 feed, 390 rows with real votes):

| Feed tag (XML) / column (CSV) | Label | Combined as |
|---|---|---|
| EarlyVotingVotes / Early Voting Votes | Early Voting | Early In-Person |
| AbsenteeBallotsVotes / Absentee Ballots Votes | Absentee Ballots | Mail (assumed) |
| ElectionDayVotes / Election Day Votes | Election Day | Election Day |
| ProvisionalVotingVotes / Provisional Voting Votes | Provisional | Provisional |

"Absentee Ballots" is taken to mean mailed ballots because early in-person
voting is its own column. That is inferred, not from a county definition.

Two differences from the Warren/Butler sample schema: the candidate total
is `<TotalVotes>` (`<Votes>` is always 0), and candidate names carry a
party prefix ("Dem Sherrod Brown"). `common/ohio_enr.py` and
`common/senate.py` handle both.

```bash
python -m counties.franklin.scraper              # download live feed
python -m counties.franklin.scraper --file x.xml # parse a local XML or CSV
python -m counties.franklin.scraper --long       # one row per vote type
```

## Automation

Runs on election night via `.github/workflows/election-night.yml`, which
commits `data/summary_wide.csv` when results change. The scraper fails if
the feed's GeneratedDate isn't 2026.
