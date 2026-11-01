"""Find each county's Nov 3, 2026 election ID on the SOS-hosted ENR.

For each county slug, request ENR/<slug>ohenr/<id>/summary_<id>.xml from a
high ID downward. A hit needs all of:
  - HTTP 200 and an ENR summary (<NewDataSet>)
  - GeneratedDate in 2026
  - a U.S. Senate race with both Brown and Husted (the general election;
    May primary files list them in separate party races)
Stops at the first hit. A file that exists but isn't a hit is recorded and
scanning continues, up to MAX_OLDER of them, since lower IDs are older.

Fetches go through the owner's Chrome window (common/sos_browser.py), 1 req/s.
Results are saved after every county to tools/enr_discovery.json, and a
rerun skips counties already done (--redo to rescan).

Don't run this on election night (Nov 3, 6 PM ET onward).

Usage:
    tools/sos_chrome.sh                     # once, from Terminal
    python -m tools.discover_enr            # all counties without a county-hosted feed
    python -m tools.discover_enr Stark Lake # just these
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from common.ohio_enr import parse
from common.sos_browser import SOSBrowser

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "enr_discovery.json"
REGISTRY = ROOT / "counties.csv"
BASE = "https://liveresults.boe.ohio.gov/ENR/{slug}ohenr/{id}/summary_{id}.{ext}"
MAX_OLDER = 3
SKIP = {"Cuyahoga", "Franklin"}  # county-hosted feeds, scraped directly
SENATE_RE = re.compile(r"\b(u\.?\s*s\.?|united\s+states)\s+senat", re.I)


def slugs(county: str) -> list[str]:
    s = county.lower()
    return [s.replace(" ", "")] + ([s.replace(" ", "_"), s.replace(" ", "-")] if " " in s else [])


def check(text: str) -> dict:
    """Classify one summary XML."""
    if "<NewDataSet" not in text[:2000]:
        return {"kind": "not_enr"}
    try:
        meta, rows, vote_types = parse(text.encode("utf-8"))
    except Exception as e:
        # Unfamiliar schema: classify from the raw text and record the error,
        # rather than stopping the whole scan.
        gen = (re.findall(r"<GeneratedDate>([^<]+)", text) or [""])[0]
        general = ("Brown" in text and "Husted" in text and bool(SENATE_RE.search(text))
                   and gen.startswith("2026"))
        return {"kind": "general" if general else "other", "generated_at": gen,
                "senate_race": "(unparsed)", "senate_races_seen": [], "vote_types": [],
                "parse_error": str(e)[:500]}
    gen = meta.get("generated_at", "")
    races: dict[str, set] = {}
    for r in rows:
        if SENATE_RE.search(r["race"]):
            races.setdefault(r["race"], set()).add(r["contestant"].lower())
    general = [n for n, c in races.items()
               if any("brown" in x for x in c) and any("husted" in x for x in c)]
    return {"kind": "general" if general and gen.startswith("2026") else "other",
            "generated_at": gen, "senate_race": general[0] if general else "",
            "senate_races_seen": sorted(races), "vote_types": vote_types}


COARSE = (40, 32, 24, 16, 8, 4, 1)  # IDs are sequential per county; find any, then the top
GAP = 3                             # consecutive 404s above the top before stopping


def discover(br: SOSBrowser, county: str) -> dict:
    """Find the county's newest election file (coarse probe, then step up to
    the top), then walk down from the top to the newest general-election file.
    Rate-limited host, so this keeps requests to roughly 6-10 per county."""
    rec = {"county": county, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "older_seen": [], "requests": 0}
    cache: dict[int, tuple[int, str]] = {}

    def get(slug, i):
        if i not in cache:
            status, _, text = br.fetch(BASE.format(slug=slug, id=i, ext="xml"))
            rec["requests"] += 1
            cache[i] = (status, text)
        return cache[i]

    for slug in slugs(county):
        cache.clear()
        found = next((i for i in COARSE if get(slug, i)[0] == 200), None)
        if found is None:
            continue
        top, misses, i = found, 0, found
        while misses < GAP:              # step up past the coarse hit
            i += 1
            if get(slug, i)[0] == 200:
                top, misses = i, 0
            else:
                misses += 1
        for i in range(top, max(top - 1 - MAX_OLDER * 2, 0), -1):
            status, text = get(slug, i)
            if status != 200:
                continue
            c = check(text)
            if c["kind"] == "general":
                csv_url = BASE.format(slug=slug, id=i, ext="csv")
                csv_status, _, csv_text = br.fetch(csv_url)
                rec["requests"] += 1
                rec.update(slug=slug, election_id=i, top_id=top,
                           xml_url=BASE.format(slug=slug, id=i, ext="xml"), csv_url=csv_url,
                           xml_ok=True, csv_ok=csv_status == 200 and "Contest Name" in csv_text[:500],
                           **{k: c[k] for k in ("generated_at", "senate_race", "vote_types")})
                return rec
            rec["older_seen"].append({"slug": slug, "id": i, **c})
            if len(rec["older_seen"]) >= MAX_OLDER:
                break
        break  # slug exists; just no general-election file among the newest
    rec["election_id"] = None
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("counties", nargs="*", help="County names (default: all except county-hosted)")
    ap.add_argument("--redo", action="store_true", help="Rescan counties already in the results file")
    args = ap.parse_args(argv)

    names = args.counties or [r["county"] for r in csv.DictReader(REGISTRY.open()) if r["county"] not in SKIP]
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [n for n in names if args.redo or n not in done]
    print(f"{len(todo)} counties to scan ({len(names) - len(todo)} already done)", file=sys.stderr)
    with SOSBrowser() as br:
        for n, county in enumerate(todo, 1):
            rec = discover(br, county)
            done[county] = rec
            OUT.write_text(json.dumps(done, indent=1, sort_keys=True))
            if rec.get("election_id"):
                print(f"[{n}/{len(todo)}] {county}: id {rec['election_id']} ({rec['slug']}) "
                      f"{rec['vote_types']} csv_ok={rec['csv_ok']}", file=sys.stderr)
            else:
                seen = [(o['id'], o.get('generated_at', '')[:10]) for o in rec["older_seen"]]
                print(f"[{n}/{len(todo)}] {county}: NO general-election file (seen: {seen or 'nothing'})",
                      file=sys.stderr)
    hits = sum(1 for r in done.values() if r.get("election_id"))
    print(f"Done: {hits}/{len(done)} counties have a Nov 3 ENR file -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
