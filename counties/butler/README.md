# Butler County, OH

**Source:** Ohio's shared election-night results feed.
Results page: https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/en/Index_24.html

The scraper tries, in order:

1. `https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/summary_24.xml`
2. `https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/summary_24.csv`

`24` is the election ID. The XML was verified against the live site on
2026-11-01 (Early Voting, Absentee Voting, Election Day, Provisional; the ENR
page's own setting names "Absentee Voting" as the mail vote).

## Output

The scraper writes the whole feed to `output/` (local, git-ignored); the
committed `data/summary_wide.csv` keeps only the U.S. Senate race
(`tools/save_senate.py`).

One row per race and choice with vote-type columns. The columns depend on
which source was used (`source_format` says which):

- **XML:** Election Day, Early Voting, Mail Ballots, Provisional, plus party,
  race/candidate IDs, winner flag and the feed's timestamp.
- **CSV:** Election Day, Absentee, Provisional. No party, IDs or timestamp;
  `pct` is computed from the race's candidate votes, and `ballots_cast`
  comes from the CSV.

Each run checks that vote types sum to the total. County-wide only; no
precinct breakdown.

```bash
python -m counties.butler.scraper              # download live feed
python -m counties.butler.scraper --file x.csv # parse a local XML or CSV
python -m counties.butler.scraper --long       # one row per vote type
```

## Automation

The SOS host blocks scripts and GitHub Actions, so this county does **not**
run in the Actions workflow. On election night `tools/local_loop.sh` runs it
(via `tools/run_sos_counties.py`) through the Chrome window opened by
`tools/sos_chrome.sh`, and commits `data/summary_wide.csv` when results
change. Status of all counties: [COUNTIES.md](../../COUNTIES.md).
