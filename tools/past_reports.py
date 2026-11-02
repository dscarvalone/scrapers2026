"""Check what format a county used for PAST election results (Nov 4, 2025
general; May 5, 2026 primary), to judge whether its Nov 3, 2026 report will
split votes by method. Counties tend to reuse the same report template.

For each county:
  - crawl the BOE results/archive pages (more pages than survey_counties),
    collecting result documents whose link or label mentions 2025 or 2026
  - for SOS-hosted sites (boe.ohio.gov/<county>), also try the standard
    /c/elecres/<YYYYMMDD>{results,precinct}.pdf paths
  - download each document and look inside the FIRST CONTEST BLOCK for
    vote-type column headers and multi-column candidate rows. (The
    statistics header at the top of a report often mentions "Absentee"
    without the candidate rows being split, which is how the earlier
    survey was misled.)

Output: tools/past_reports.json (excerpts included for manual review).
Usage:
    python -m tools.past_reports Fairfield Richland ...
"""

from __future__ import annotations

import csv
import html as htmlmod
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from tools.survey_counties import Fetcher, text_of

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("PAST_OUT", ROOT / "tools" / "past_reports.json"))
MAX_PAGES, MAX_DOCS = 8, 8
PAGE_WORDS = re.compile(r"result|archive|past|previous|election[-_ ]?info|canvass", re.I)
DOC_EXT = re.compile(r"\.(pdf|xlsx?|csv|htm|html|txt)(\?|$)", re.I)
YEAR = re.compile(r"2025|2026|25G|26P|G25|P26|110425|050526|11[-_.]?4[-_.]?25|5[-_.]?5[-_.]?26", re.I)
RESULTISH = re.compile(r"result|summary|canvass|official|unofficial|election night|cumulative|report", re.I)
SOS_DATES = ["20251104", "20260505"]
METHOD_HDR = re.compile(r"election\s*day|absentee|early|by\s*mail|provisional|in[-\s]?person|polls|walk[-\s]?in|"
                        r"\bAB\b|\bED\b|\bEV\b|\bPR\b|vote\s*center", re.I)
CONTEST_START = re.compile(r"vote\s+for\s+(not\s+more\s+than\s+)?\d+|\(vote for \d+\)", re.I)
NUMTOK = re.compile(r"^\d[\d,]*$")


def analyze(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    starts = [i for i, l in enumerate(lines) if CONTEST_START.search(l)]
    if not starts:
        return {"contest_found": False}
    i = starts[0]
    block = lines[max(0, i - 3): i + 25]
    hdr_words = sorted({m.group(0) for l in block[:14] for m in METHOD_HDR.finditer(l)}, key=str.lower)
    # Widest candidate row in the block: count numeric tokens (excluding %).
    widths = []
    for l in block:
        toks = l.replace("\u00a0", " ").split()
        widths.append(sum(1 for t in toks if NUMTOK.match(t)))
    # Dominion-style one-value-per-line layouts: count numeric lines after a name.
    run, best_run = 0, 0
    for l in block:
        if NUMTOK.match(l) or l.endswith("%"):
            run += 1
            best_run = max(best_run, run)
        else:
            run = 0
    max_cols = max(max(widths), best_run - 1)  # minus the % line
    return {"contest_found": True, "method_header_words": hdr_words, "max_numeric_cols": max_cols,
            "likely_split": bool(hdr_words) and max_cols >= 3,
            "excerpt": " | ".join(block[:18])[:900]}


def collect(f: Fetcher, boe_url: str) -> tuple[list[dict], list[dict]]:
    site = urlparse(boe_url).netloc.lower().removeprefix("www.")
    queue, seen, pages, docs = [boe_url], set(), [], {}
    while queue and len(pages) < MAX_PAGES:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            final, html, via = f.page(u)
        except Exception as e:
            pages.append({"url": u, "error": str(e)[:150]})
            continue
        pages.append({"url": final, "via": via})
        for href, label in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            link = urljoin(final, htmlmod.unescape(href.strip()))
            label = htmlmod.unescape(re.sub(r"<[^>]+>|\s+", " ", label)).strip()[:90]
            p = urlparse(link)
            if p.scheme not in ("http", "https"):
                continue
            blob = link + " " + label
            if (DOC_EXT.search(p.path) or "dropbox.com" in p.netloc) and YEAR.search(blob) and RESULTISH.search(blob):
                docs.setdefault(link, label)
            elif p.netloc.lower().removeprefix("www.") == site and PAGE_WORDS.search(p.path + " " + label) \
                    and not DOC_EXT.search(p.path):
                queue.append(link.split("#")[0])
    return pages, [{"url": u, "label": l} for u, l in docs.items()]


def rank(d: dict) -> int:
    b = (d["url"] + " " + d["label"]).lower()
    score = 0
    score += 3 if "unofficial" in b or "election night" in b or "cumulative" in b else 0
    score += 2 if "summary" in b or "results" in b else 0
    score += 2 if "group" in b or "detail" in b else 0
    score -= 3 if "precinct" in b or "sovc" in b or "statement of votes" in b else 0
    score -= 4 if "audit" in b or "notice" in b or "candidate" in b else 0
    return -score


def main(argv=None) -> int:
    names = (argv if argv is not None else sys.argv[1:])
    boe = {r["county"]: r["boe_url"] for r in csv.DictReader((ROOT / "counties.csv").open())}
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    for county in names:
        if county in done:
            continue
        f = Fetcher()
        try:
            url = boe[county]
            pages, docs = collect(f, url)
            if "boe.ohio.gov" in url:
                slug = county.lower().replace(" ", "")
                base = f"https://www.boe.ohio.gov/{slug}/c/elecres/"
                for d in SOS_DATES:
                    docs.append({"url": f"{base}{d}results.pdf", "label": f"(standard SOS path) {d} results"})
            docs = sorted({d["url"]: d for d in docs}.values(), key=rank)[:MAX_DOCS]
            out = []
            for d in docs:
                url_d = d["url"].replace("dl=0", "dl=1")
                try:
                    status, ctype, data, via = f.doc(url_d)
                    rec = {**d, "status": status, "type": ctype[:30], "bytes": len(data), "via": via}
                    if status == 200 and len(data) > 500:
                        rec.update(analyze(text_of(ctype, data)))
                except Exception as e:
                    rec = {**d, "error": str(e)[:150]}
                out.append(rec)
        finally:
            f.close()
        done[county] = {"pages": pages, "docs": out}
        OUT.write_text(json.dumps(done, indent=1))
        split = [d for d in out if d.get("likely_split")]
        print(f"{county}: {len(pages)} pages, {len(out)} docs checked, {len(split)} look split"
              + (f" e.g. {split[0]['label'][:50]!r} {split[0]['method_header_words']}" if split else ""),
              file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
