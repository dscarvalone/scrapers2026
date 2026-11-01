# Warren County, OH

**Source:** Ohio's shared election-night results feed:
https://liveresults.boe.ohio.gov/ENR/warrenohenr/18/summary_18.xml

`18` is the election ID; a future election will have a different number, so
pass the new URL with `--url` or update `URL` in `scraper.py`.

## Output

One row per race and contestant, with a column for each vote type: Election
Day, Early Voting, Mail Ballots, Provisional, plus the total, percentage,
winner flag, race-level over/under votes, precincts reported, and the feed's
generated timestamp. Each run checks that vote types sum to the total.

The feed is county-wide only; it has no precinct breakdown.

```bash
python -m counties.warren.scraper              # download live XML
python -m counties.warren.scraper --file x.xml # parse a local copy
python -m counties.warren.scraper --long       # one row per vote type
```

## Automation

Runs on election night via `.github/workflows/election-night.yml`, which
commits `data/summary_wide.csv` when results change.
