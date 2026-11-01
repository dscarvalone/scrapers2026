# Franklin County, OH

**Status:** source identified, no scraper yet.

**Results page:** https://vote.franklincountyohio.gov/elections

The results page shows each candidate's votes split into absentee and election
day, plus precincts reporting (889 precincts). Next step: find the data feed
behind the page (DevTools → Network → Fetch/XHR, watching for requests that
repeat on a timer) or a downloadable export, then build `scraper.py` here.
