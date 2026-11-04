"""Senate results in the AP county aggregator's column layout (its `county_raw`
tab), so the two sheets line up column for column.

Same names, order and definitions as the aggregator, for the columns we can
fill from our own sources; its model columns (exp_*, expected turnout,
history, demographics) are left out. Definitions, checked against the
aggregator's own rows:
    dem_margin     dem_votes - gop_votes            (votes)
    two_way        dem / (dem + gop)                (0-1)
    <x>_share      <x>_votes / total_votes          (0-1)
    pct_<m>        <m>_total_votes / total_votes    (0-1)
    early          votes cast before Election Day (evip + vbm, plus late-
                   arriving mail where a county reports it separately)
Party columns: dem = Brown, gop = Husted, breakout_1 = Redpath (Lib),
breakout_2 = Levy (ASSUMED: the aggregator's Ind column), other = write-ins.

Rows: Statewide first, then the 88 counties alphabetically, like the aggregator.

Where the numbers come from (method_source):
  itemized        the county's own vote-method split. total_votes and
                  precincts from that same feed, so methods sum to the total.
  first_drop      ESTIMATE for counties with totals only (common/timing.py):
                  eday and early only; evip / vbm / provisional blank.
                  Totals and precincts from the SOS statewide site.
  totals_only     no split yet: toplines only.
A county whose own feed is stale (the SOS site is more than 1,000 votes and
5% ahead of it, common.timing.stale_feed; e.g. its PDF is still the zero
report) is treated as if it had no feed: first_drop or totals_only from the
SOS site, with a note. Its own split comes back once its feed catches up.
The Statewide row sums every county's toplines; its method columns sum only
the counties that have that method (coverage in `notes`).

latest_data_as_of = the last time this county's Senate numbers CHANGED (ET),
not the last time we fetched them: for itemized counties from
tools/build_method_workbook.changed_at (a per-county record of the numbers),
for the rest from the statewide snapshot log. The Statewide row shows the
most recent county change.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.timing import CAND_COL, PARTY_COLS, stale_feed

ROOT = Path(__file__).resolve().parent.parent
STATEWIDE = ROOT / "results" / "senate_statewide_by_county.csv"
ET = ZoneInfo("America/New_York")
METHODS = ["eday", "evip", "vbm", "provisional", "early"]

TOPLINE = ["state_code", "county_fips", "reporting_unit_name", "reporting_status", "latest_data_as_of",
           "refreshed_sheet_as_of", "total_votes", "pct_precincts_in", "dem_margin", "two_way",
           "dem_votes", "gop_votes", "breakout_1_votes", "breakout_2_votes", "other_votes",
           "dem_share", "gop_share", "breakout_1_share", "breakout_2_share", "other_share"]


def method_cols(m: str) -> list[str]:
    return ([f"{m}_total_votes", f"pct_{m}"] + [f"{m}_{p}_votes" for p in PARTY_COLS]
            + [f"{m}_dem_margin", f"{m}_two_way"] + [f"{m}_{p}_share" for p in PARTY_COLS])


EXTRA = ["method_source", "has_mail_inperson_split", "precincts_reported", "precincts_total", "notes",
         # the county's latest change in the SOS statewide totals (common.timing.latest_batch)
         "batch_dem_votes", "batch_gop_votes", "batch_total_votes", "batch_as_of"]
COLUMNS = TOPLINE + [c for m in METHODS for c in method_cols(m)] + EXTRA


def _ratio(a, b):
    return round(a / b, 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b else ""


def _parse_time(s: str):
    """Our timestamps (ET text, ISO with offset) -> naive ET datetime, or ''."""
    if not s:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S %Z",):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s).astimezone(ET).replace(tzinfo=None)
    except ValueError:
        return ""


def _status(reported, total, votes) -> str:
    try:
        reported, total = int(reported), int(total)
    except (TypeError, ValueError):
        return "Reporting In Progress" if votes else "Not Started"
    if total and reported >= total:
        return "Fully Reported"
    if reported > 0 or votes:
        return "Reporting In Progress"
    return "Not Started"


def _fill_block(out: dict, m: str, by_party: dict) -> None:
    """by_party: {dem: n, gop: n, ...}. Fills <m>_* votes, margin, two-way, shares."""
    tot = sum(by_party.get(p, 0) for p in PARTY_COLS)
    out[f"{m}_total_votes"] = tot
    for p in PARTY_COLS:
        out[f"{m}_{p}_votes"] = by_party.get(p, 0)
        out[f"{m}_{p}_share"] = _ratio(by_party.get(p, 0), tot)
    d, g = by_party.get("dem", 0), by_party.get("gop", 0)
    out[f"{m}_dem_margin"] = d - g
    out[f"{m}_two_way"] = _ratio(d, d + g)


def _fill_timing(out: dict, t: dict) -> None:
    """eday and early blocks from a votes_by_timing row (skips a class it lacks)."""
    for m, cls in (("eday", "eday"), ("early", "pre_eday")):
        if t.get(f"{cls}_total_votes", "") != "":
            _fill_block(out, m, {p: t[f"{cls}_{p}_votes"] for p in PARTY_COLS})


def _fill_toplines(out: dict, by_party: dict) -> None:
    tot = sum(by_party.get(p, 0) for p in PARTY_COLS)
    out["total_votes"] = tot
    for p in PARTY_COLS:
        out[f"{p}_votes"] = by_party.get(p, 0)
        out[f"{p}_share"] = _ratio(by_party.get(p, 0), tot)
    d, g = by_party.get("dem", 0), by_party.get("gop", 0)
    out["dem_margin"] = d - g
    out["two_way"] = _ratio(d, d + g)


def statewide_by_county(path: Path = STATEWIDE) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for r in csv.DictReader(path.open(newline="", encoding="utf-8")):
        c = out.setdefault(r["county"].strip(), {"votes": {}, "precincts_reported": r["precincts_reported"],
                                                  "precincts_total": r["precincts_total"],
                                                  "fetched_at": r["fetched_at"]})
        p = CAND_COL.get(r["candidate"])
        if p:
            c["votes"][p] = c["votes"].get(p, 0) + int(r["votes"] or 0)
    return out


def county_rows(reg: list[dict], wide: list[dict], timing: list[dict], fetched: dict,
                statewide: dict[str, dict], built: datetime, batches: dict | None = None) -> list[dict]:
    """reg: counties.csv rows; wide: votes_by_method rows; timing: votes_by_timing
    rows; fetched: {county: (ET text, basis)}; statewide: statewide_by_county();
    batches: common.timing.latest_batch()."""
    wide_by = {r["county"]: r for r in wide}
    tim_by = {r["county"]: r for r in timing}
    rows = []
    for g in sorted(reg, key=lambda r: r["county"]):
        c = g["county"]
        out = {k: "" for k in COLUMNS}
        out.update(state_code="OH", county_fips=g["county_fips"], reporting_unit_name=f"{c} County",
                   refreshed_sheet_as_of=built)
        w, t, s = wide_by.get(c, {}), tim_by.get(c, {}), statewide.get(c)
        notes = []
        stale = False
        if w.get("itemized") and s and s["votes"]:
            feed = sum(w[f"{b}_total_votes"] or 0 for b in ("eday", "early", "provisional", "unassigned")
                       if w.get(f"{b}_total_votes", "") != "")
            stale = stale_feed(feed, sum(s["votes"].values()))
            if stale and "feed stale" not in (t.get("notes") or ""):
                notes.append(f"county feed stale ({feed:,} votes vs {sum(s['votes'].values()):,} on the SOS "
                             "site): toplines from the SOS site, its own split not used")
        if w.get("itemized") and not stale:
            out["method_source"] = "itemized"
            out["has_mail_inperson_split"] = bool(t.get("has_mail_inperson_split"))
            # Toplines from the same feed as the split, so methods add up.
            party = {p: sum(w[f"{b}_{p}_votes"] or 0 for b in ("eday", "early", "provisional", "unassigned")
                            if w[f"{b}_total_votes"] != "") for p in PARTY_COLS}
            # early columns in votes_by_method are evip+vbm (or the combined
            # number); unassigned late mail counts as early here (timing model).
            _fill_toplines(out, party)
            _fill_timing(out, t)
            for m in ("evip", "vbm", "provisional"):
                if w[f"{m}_total_votes"] != "":
                    _fill_block(out, m, {p: w[f"{m}_{p}_votes"] for p in PARTY_COLS})
            if t.get("unclassified_total_votes") not in ("", None, 0):
                notes.append(f"{t['unclassified_total_votes']:,} votes of unknown timing in total_votes only")
            out["precincts_reported"], out["precincts_total"] = w["precincts_reported"], w["precincts_total"]
            if not _int(out["precincts_total"]) and s:
                # Some feeds (Cuyahoga, Summit) carry no precinct counts.
                out["precincts_reported"], out["precincts_total"] = s["precincts_reported"], s["precincts_total"]
                notes.append("precincts from the SOS statewide site")
            out["latest_data_as_of"] = _parse_time(fetched.get(c, ("", ""))[0] or w.get("fetched_at", ""))
            if s and s["votes"]:
                sw = sum(s["votes"].values())
                if sw != out["total_votes"]:
                    notes.append(f"statewide site shows {sw:,} total votes")
        elif s:
            _fill_toplines(out, s["votes"])
            out["precincts_reported"], out["precincts_total"] = s["precincts_reported"], s["precincts_total"]
            # Last CHANGE of this county's statewide totals: the timing model's
            # as_of is its latest entry in results/statewide_snapshots.csv,
            # which logs a county only when its numbers change.
            out["latest_data_as_of"] = _parse_time(t.get("as_of") or "") or _parse_time(s["fetched_at"])
            if t.get("timing_source") == "first_drop":
                out["method_source"] = "first_drop"
                out["has_mail_inperson_split"] = False
                _fill_timing(out, t)
                notes.append("eday/early ESTIMATED from the first report with 0 precincts in")
            else:
                out["method_source"] = "totals_only"
        else:
            out["method_source"] = "totals_only"
            notes.append("no statewide totals yet")
        if t.get("notes"):
            notes.append(t["notes"])
        out["pct_precincts_in"] = _ratio(_int(out["precincts_reported"]), _int(out["precincts_total"]))
        out["reporting_status"] = _status(out["precincts_reported"], out["precincts_total"], out["total_votes"])
        for m in METHODS:
            out[f"pct_{m}"] = _ratio(out[f"{m}_total_votes"], out["total_votes"])
        out["notes"] = "; ".join(notes)
        b = (batches or {}).get(c)
        if b:
            out.update(batch_dem_votes=b["dem"], batch_gop_votes=b["gop"], batch_total_votes=b["total"],
                       batch_as_of=_utc_to_et_text(b["at"]))
        rows.append(out)
    return [statewide_row(rows, built, statewide)] + rows


def _utc_to_et_text(s: str) -> str:
    """Snapshot timestamp (ISO, UTC) -> 'YYYY-MM-DD HH:MM:SS' Eastern, like the other as-of columns."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(s).astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return s


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return ""


def statewide_row(rows: list[dict], built: datetime, statewide: dict[str, dict] | None = None) -> dict:
    out = {k: "" for k in COLUMNS}
    out.update(state_code="OH", reporting_unit_name="Statewide", refreshed_sheet_as_of=built)
    _fill_toplines(out, {p: sum(r[f"{p}_votes"] or 0 for r in rows) for p in PARTY_COLS})
    # Precincts: the SOS statewide site has all 88 counties; county rows otherwise.
    src = list(statewide.values()) if statewide and len(statewide) == len(rows) else rows
    out["precincts_reported"] = sum(_int(r["precincts_reported"]) or 0 for r in src)
    out["precincts_total"] = sum(_int(r["precincts_total"]) or 0 for r in src)
    out["pct_precincts_in"] = _ratio(out["precincts_reported"], out["precincts_total"])
    out["reporting_status"] = _status(out["precincts_reported"], out["precincts_total"], out["total_votes"])
    times = [r["latest_data_as_of"] for r in rows if isinstance(r["latest_data_as_of"], datetime)]
    out["latest_data_as_of"] = max(times) if times else ""
    notes = []
    for m in METHODS:
        have = [r for r in rows if r[f"{m}_total_votes"] != ""]
        if have:
            _fill_block(out, m, {p: sum(r[f"{m}_{p}_votes"] for r in have) for p in PARTY_COLS})
            out[f"pct_{m}"] = ""   # partial coverage: a share of the state total would mislead
            notes.append(f"{m}: {len(have)} counties")
    out["method_source"] = "sum of counties"
    out["notes"] = ("method columns sum only counties that report that method (" + ", ".join(notes) + ")"
                    if notes else "")
    return out
