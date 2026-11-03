"""Election-night recheck: which still-unknown counties now publish the U.S.
Senate vote split by method?

For each county in counties.csv that has no method-split scraper and isn't
confirmed totals-only, fetch its SOS-hosted election-night PDF
    https://www.boe.ohio.gov/<slug>/c/elecres/20261103results.pdf
through the Chrome window (tools/sos_chrome.sh), and try the PDF layouts on
the Senate block (positional = ES&S/Electionware, dominion). Reports, per
county: no file / TOTAL only / SPLIT (with columns), and whether real votes
are in yet. Counties whose BOE site isn't SOS-hosted are listed for a manual
look, since their election-night address isn't predictable.

With --make-scrapers, a scraper is generated (tools/make_pdf_scraper.py) for
every SPLIT county, so tools/local_loop.sh picks it up on its next cycle.

Then the PRECINCT PDF (.../20261103precinct.pdf) of every SOS-hosted county
without a scraper, including "confirmed totals only" ones (that status came
from the cumulative PDF). Each is classified: SPLIT (Senate rows carry
vote-type columns) / total_only / ballots_by_mode_only (turnout by mode, no
contests, e.g. Gallia's zero report) / no_senate / no_file / unparsed.
Report only: a precinct report needs a precinct-summing scraper.

Output: tools/recheck_<YYYYmmdd_HHMM>.json and a summary on stderr.
Usage (Terminal, with the Chrome window open):
    python -m tools.recheck_zero_reports                  # check only
    python -m tools.recheck_zero_reports --make-scrapers  # check + generate scrapers
    python -m tools.recheck_zero_reports Logan Darke      # just these
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from common.pdf_results import parse_positional, parse_dominion, pdf_text
from common.sos_browser import fetch_file_via_page
from tools.make_pdf_scraper import make

ROOT = Path(__file__).resolve().parent.parent
DONE_CLASSES = {"A_county_feed_scriptable", "A2_sos_enr_via_browser", "A3_enhanced_voting",
                "A4_county_pdf_via_browser", "A5_clarity", "A6_pdf_link_on_election_night",
                "N_confirmed_totals_only"}
LEAN_ORDER = {"likely_yes": 0, "possible": 1, "leaning_no": 2, "no_evidence": 3}


def targets(names: list[str]) -> list[dict]:
    rows = list(csv.DictReader((ROOT / "counties.csv").open()))
    verdicts = json.loads((ROOT / "tools" / "survey60_verdicts.json").read_text())
    out = []
    for r in rows:
        if names and r["county"] not in names:
            continue
        if not names and r["access_class"] in DONE_CLASSES:
            continue
        lean = (verdicts.get(r["county"]) or {}).get("lean") or ""
        out.append({"county": r["county"], "boe_url": r["boe_url"], "lean": lean,
                    "sos": "boe.ohio.gov" in r["boe_url"] or r["boe_host"] == "sos"})
    return sorted(out, key=lambda t: (LEAN_ORDER.get(t["lean"], 4), t["county"]))


def check(county: str) -> dict:
    slug = county.lower().replace(" ", "")
    url = f"https://www.boe.ohio.gov/{slug}/c/elecres/20261103results.pdf"
    page = f"https://www.boe.ohio.gov/{slug}/election-info/election-results/"
    rec = {"url": url}
    try:
        data = fetch_file_via_page(url, page)
    except Exception as e:
        rec.update(status="no_file", detail=str(e)[:150])
        return rec
    for layout, fn in (("positional", lambda d: parse_positional(d)), ("dominion", lambda d: parse_dominion(pdf_text(d)))):
        try:
            race, rows, cols = fn(data)
        except Exception as e:
            rec.setdefault("errors", {})[layout] = str(e)[:150]
            continue
        votes = sum(r["total"] for r in rows)
        rec.update(layout=layout, race=race, cols=cols, candidates=[r["contestant"] for r in rows],
                   senate_votes=votes, status="SPLIT" if cols else "total_only")
        if cols:
            bad = [r["contestant"] for r in rows if sum(r[c] for c in cols) != r["total"]]
            rec["sum_ok"] = not bad
            break
    rec.setdefault("status", "unparsed")
    return rec


SENATE_RE = re.compile(r"(U\.?\s?S\.?\s+Senat\w*|United States Senat\w*)", re.I)
# vote-type column words, matched as whole words on whitespace-collapsed text.
# Long forms case-insensitive; 2-letter codes (Highland: AB ED EV PR) case-sensitive.
METHOD_RE = re.compile(r"\b(Election Day|Absentee|Early Vot\w*|Early|Provisional|Prov|Mail|In[- ]Office|"
                       r"In[- ]Person|Polls)\b", re.I)
CODE_RE = re.compile(r"(?<![A-Za-z])(AB|ED|EV|PR)(?![A-Za-z])")
NUM_RE = re.compile(r"(?<![\d.,%])\d[\d,]*(?![\d.,]*%)(?![\d.])")


def analyze_precinct(text: str) -> dict:
    """Classify a precinct-detail PDF's text: does the U.S. Senate race carry
    vote-type columns? Split = 3+ vote numbers between 'Brown' and 'Husted'
    (total + 2 or more vote types; percentages ignored) and 2+ vote-type words
    around the race (including the page header above it). A precinct report
    repeats the race once per precinct; one split block is enough."""
    flat = re.sub(r"\s+", " ", text)
    blocks = list(SENATE_RE.finditer(flat))

    def words_in(s):
        found = {m.group(1).title() for m in METHOD_RE.finditer(s)} | set(CODE_RE.findall(s))
        return sorted(found)

    if not blocks:
        w = words_in(flat)
        return {"status": "ballots_by_mode_only" if len(w) >= 2 else "no_senate", "cols": w, "blocks": 0}
    split_cols, max_votes = None, 0
    for m in blocks:
        window = flat[max(0, m.start() - 400): m.start() + 900]
        cand = re.search(r"Brown(.*?)Husted", flat[m.start(): m.start() + 900], re.I)
        if not cand:
            continue
        nums = [int(x.replace(",", "")) for x in NUM_RE.findall(cand.group(1))]
        max_votes = max([max_votes] + nums)
        w = words_in(window)
        if len(nums) >= 3 and len(w) >= 2:
            split_cols = w
    return {"status": "SPLIT" if split_cols else "total_only", "cols": split_cols or [],
            "blocks": len(blocks), "votes_in": max_votes > 0}


def check_precinct(county: str) -> dict:
    slug = county.lower().replace(" ", "")
    url = f"https://www.boe.ohio.gov/{slug}/c/elecres/20261103precinct.pdf"
    page = f"https://www.boe.ohio.gov/{slug}/election-info/election-results/"
    rec = {"url": url}
    try:
        data = fetch_file_via_page(url, page)
    except Exception as e:
        rec.update(status="no_file", detail=str(e)[:150])
        return rec
    if data[:4] != b"%PDF":  # the site's 404 page
        rec.update(status="no_file", detail="not a PDF (no precinct report posted)")
        return rec
    try:
        rec.update(analyze_precinct(pdf_text(data)))
    except Exception as e:  # scanned / not a PDF
        rec.update(status="unparsed", detail=str(e)[:150])
    return rec


def precinct_targets(names: list[str]) -> list[str]:
    """SOS-hosted counties with no method-split scraper, INCLUDING confirmed totals-only ones:
    that status came from the cumulative results PDF, not the precinct PDF."""
    rows = list(csv.DictReader((ROOT / "counties.csv").open()))
    keep = (DONE_CLASSES - {"N_confirmed_totals_only"})
    return sorted(r["county"] for r in rows
                  if (r["county"] in names if names else r["access_class"] not in keep)
                  and ("boe.ohio.gov" in r["boe_url"] or r["boe_host"] == "sos"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("counties", nargs="*")
    ap.add_argument("--make-scrapers", action="store_true")
    args = ap.parse_args(argv)
    todo = targets(args.counties)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = ROOT / "tools" / f"recheck_{stamp}.json"
    results, manual = {}, []
    print(f"Rechecking {len(todo)} counties", file=sys.stderr, flush=True)
    for t in todo:
        if not t["sos"]:
            manual.append(t)
            continue
        rec = check(t["county"])
        rec["lean"] = t["lean"]
        results[t["county"]] = rec
        out_path.write_text(json.dumps({"results": results, "manual": manual}, indent=1))
        extra = (f" {rec['layout']} cols={rec['cols']} votes={rec['senate_votes']}"
                 + ("" if rec.get("sum_ok", True) else " SUM MISMATCH")) if rec["status"] == "SPLIT" else ""
        print(f"  {t['county']:12} [{t['lean'] or '-':11}] {rec['status']}{extra}", file=sys.stderr, flush=True)
        if args.make_scrapers and rec["status"] == "SPLIT" and rec.get("sum_ok", True):
            p = make(t["county"], rec["layout"], ", ".join(rec["cols"]))
            print(f"      -> scraper {p.relative_to(ROOT)}", file=sys.stderr, flush=True)
        time.sleep(1)
    precinct = {}
    ptodo = precinct_targets(args.counties)
    print(f"\nPrecinct PDFs: checking {len(ptodo)} SOS-hosted counties without a scraper", file=sys.stderr, flush=True)
    for c in ptodo:
        rec = check_precinct(c)
        precinct[c] = rec
        out_path.write_text(json.dumps({"results": results, "precinct": precinct, "manual": manual}, indent=1))
        extra = (f" cols={rec['cols']}" + (" votes in" if rec.get("votes_in") else " (zero report)")) \
            if rec["status"] == "SPLIT" else ""
        print(f"  {c:12} precinct: {rec['status']}{extra}", file=sys.stderr, flush=True)
        time.sleep(1)
    split = [c for c, r in results.items() if r["status"] == "SPLIT"]
    psplit = [c for c, r in precinct.items() if r["status"] == "SPLIT"]
    print(f"\nSPLIT ({len(split)}): {', '.join(split) or 'none'}", file=sys.stderr)
    print(f"SPLIT in the precinct PDF only ({len(psplit)}; needs a precinct-summing scraper, not auto-built): "
          f"{', '.join(psplit) or 'none'}", file=sys.stderr)
    print(f"Not SOS-hosted, check by hand ({len(manual)}): "
          + ", ".join(f"{m['county']} ({m['boe_url']})" for m in manual), file=sys.stderr)
    print(f"Details: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
