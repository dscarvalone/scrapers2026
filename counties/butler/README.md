# Butler County, OH

**Source:** Ohio's shared election-night results feed.
Results page: https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/en/Index_24.html

The scraper tries, in order:

1. `https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/summary_24.xml`
2. `https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/summary_24.csv`

Both URLs follow the platform's pattern (as seen for Warren) but haven't been
checked against the live site yet. `24` is the election ID.

## Output

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

Runs on election night via `.github/workflows/election-night.yml`, which
commits `data/summary_wide.csv` when results change.
