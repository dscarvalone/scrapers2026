# Warren County, OH

**Source:** Ohio's shared election-night results feed:
https://liveresults.boe.ohio.gov/ENR/warrenohenr/18/summary_18.xml

`18` is the election ID; a future election will have a different number, so
pass the new URL with `--url` or update `URL` in `scraper.py`.

## Output

The scraper writes the whole feed to `output/` (local, git-ignored); the
committed `data/summary_wide.csv` keeps only the U.S. Senate race
(`tools/save_senate.py`).

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

The SOS host blocks scripts and GitHub Actions, so this county does **not**
run in the Actions workflow. On election night `tools/local_loop.sh` runs it
(via `tools/run_sos_counties.py`) through the Chrome window opened by
`tools/sos_chrome.sh`, and commits `data/summary_wide.csv` when results
change. Verified against the live feed on 2026-11-01. Status of all
counties: [COUNTIES.md](../../COUNTIES.md).
