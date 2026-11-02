# Cuyahoga County, OH

**Source:** the county's "All Results" Excel export, hosted by Enhanced Voting:
https://app.enhancedvoting.com/cdn/results/6397b9a7-ccfa-406e-a155-6d2a595cf70d/All%20Results_6c376c4d-15e5-4aec-83b0-0e4cfeec59cb.xlsx

The URL contains generated IDs and may change; pass a new one with `--url`.

## Output

The scraper writes the whole feed to `output/` (local, git-ignored); the
committed `data/summary_wide.csv` keeps only the U.S. Senate race
(`tools/save_senate.py`).

One row per contest and choice, with a column for each vote type: Election
Day, Early In-Person, Vote By Mail, Provisional, Post Election Day, Post VBM,
and a total. Ballots Cast, Over Votes and Under Votes rows are marked in
`row_type`. Each run checks that vote-type sums match the county's own totals.

```bash
python -m counties.cuyahoga.scraper               # county-wide, wide format
python -m counties.cuyahoga.scraper --precincts   # adds ~160k precinct rows (~1 min)
python -m counties.cuyahoga.scraper --long        # one row per vote type
python -m counties.cuyahoga.scraper --file x.xlsx # parse a local copy
```

Local runs write `output/<name>_latest.csv` plus a timestamped copy.

## Automation

Runs on election night via `.github/workflows/election-night.yml`, which
commits `data/summary_wide.csv` when results change. Precinct output is
available locally with `--precincts` but isn't part of the automated run.
