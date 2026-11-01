"""Look for Clarity (Scytl) results sites for counties without a method-split
scraper. Hamilton's Clarity site (results.votehamiltoncountyohio.gov) was
missed by tools/survey_counties.py, so this checks two Clarity patterns
directly, with plain HTTP and one request at a time:

  1. https://results.enr.clarityelections.com/OH/<County>/   (Clarity-hosted)
  2. https://results.<county BOE domain>/OH/<County>/          (custom domain, like Hamilton)

For a hit, the county's election list is read to find a Nov 3, 2026 election
ID, which current_ver.txt confirms. Output: tools/clarity_probe.json.

Usage:
    python -m tools.probe_clarity            # all counties not yet itemized
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "clarity_probe.json"
UA = {"User-Agent": "scrapers2026 (election results research)"}
ITEMIZED_CLASSES = {"A_county_feed_scriptable", "A2_sos_enr_via_browser", "A3_enhanced_voting",
                    "A4_county_pdf_via_browser", "A5_clarity"}


def get(url):
    time.sleep(1.2)
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        return r.status_code, r.url, r.text
    except Exception as e:
        return None, url, str(e)


def candidates(county: str, boe_url: str) -> list[str]:
    slug = county.replace(" ", "_")
    out = [f"https://results.enr.clarityelections.com/OH/{slug}/"]
    host = urlparse(boe_url).netloc.lower().removeprefix("www.")
    if host and "boe.ohio.gov" not in host:
        root = ".".join(host.split(".")[-2:]) if not host.endswith(".oh.us") else host
        out.append(f"https://results.{root}/OH/{slug}/")
    return out


def main() -> int:
    rows = list(csv.DictReader((ROOT / "counties.csv").open()))
    todo = [(r["county"], r["boe_url"]) for r in rows if r["access_class"] not in ITEMIZED_CLASSES
            and r["county"] != "Hamilton"]
    res = {}
    for county, boe in todo:
        rec = {"county": county, "tried": []}
        for u in candidates(county, boe):
            s, final, text = get(u)
            rec["tried"].append([u, s])
            if s == 200 and ("clarity" in text.lower() or "Election Night Reporting" in text):
                ids = sorted(set(re.findall(r"/OH/[^/\"']+/(\d{5,7})/", text + final)), key=int)
                rec.update(hit=u, final=final, election_ids=ids[-5:])
                for eid in reversed(ids[-5:]):
                    base = re.sub(r"/OH/([^/]+)/.*", rf"/OH/\1/{eid}", final)
                    s2, _, ver = get(f"{base}/current_ver.txt")
                    s3, _, settings = get(f"{base}/{ver.strip()}/json/en/electionsettings.json") if s2 == 200 else (None, "", "")
                    if s3 == 200 and ("2026" in settings and ("11/3" in settings or "11-3" in settings or "November 3" in settings)):
                        rec.update(base=base, version=ver.strip())
                        break
                break
        res[county] = rec
        OUT.write_text(json.dumps(res, indent=1))
        print(f"{county}: {rec.get('base') or rec.get('hit') or 'no Clarity site'}", file=sys.stderr, flush=True)
    hits = [c for c, r in res.items() if r.get("base")]
    print(f"Done: {len(hits)} with a Nov 3 Clarity election: {hits}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
