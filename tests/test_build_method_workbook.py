"""Bucket math for tools/build_method_workbook.vote_rows, on made-up numbers."""

from tools.build_method_workbook import vote_rows

REG = [{"county": "Split", "county_fips": "39001"},
       {"county": "Combined", "county_fips": "39003"},
       {"county": "None", "county_fips": "39005"}]


def row(county, cand, method, label, votes):
    return {"county": county, "candidate": cand, "method": method, "method_county_label": label,
            "votes": votes, "precincts_reported": "1", "precincts_total": "2", "source_generated_at": "t"}


LONG = [
    row("Split", "Sherrod Brown", "Election Day", "Election Day", 100),
    row("Split", "Sherrod Brown", "Early In-Person", "Early Voting", 30),
    row("Split", "Sherrod Brown", "Mail", "Mail Ballots", 20),
    row("Split", "Sherrod Brown", "Provisional", "Provisional", 2),
    row("Split", "Sherrod Brown", "Post VBM", "Post VBM", 5),
    row("Split", "Jon Husted", "Election Day", "Election Day", 90),
    row("Split", "Jon Husted", "Early In-Person", "Early Voting", 10),
    row("Split", "Jon Husted", "Mail", "Mail Ballots", 15),
    row("Split", "Jon Husted", "Provisional", "Provisional", 1),
    row("Split", "Jon Husted", "Post VBM", "Post VBM", 0),
    row("Split", "Greg Levy", "Election Day", "Election Day", 4),
    row("Split", "Write-in", "Mail", "Mail Ballots", 1),
    row("Combined", "Sherrod Brown", "Election Day", "Election", 50),
    row("Combined", "Sherrod Brown", "Absentee (early in-person + mail)", "Early", 25),
    row("Combined", "Jon Husted", "Election Day", "Election", 60),
    row("Combined", "Jon Husted", "Absentee (early in-person + mail)", "Early", 15),
]


def test_buckets():
    wide, tidy = vote_rows(REG, LONG)
    s, c, n = wide
    assert s["itemized"] and s["eday_total_votes"] == 194 and s["eday_breakout_2_votes"] == 4
    assert s["evip_dem_votes"] == 30 and s["vbm_gop_votes"] == 15 and s["vbm_other_votes"] == 1
    assert s["early_dem_votes"] == 50 and s["early_total_votes"] == 76  # evip + vbm
    assert s["unassigned_dem_votes"] == 5 and s["unassigned_labels"] == "Post VBM"
    assert s["method_sum_total_votes"] == 194 + 76 + 3 + 5
    assert s["early_combined_only"] is False
    # combined-only county: early filled, evip/vbm blank (not reported), not 0
    assert c["early_total_votes"] == 40 and c["evip_total_votes"] == "" and c["vbm_dem_votes"] == ""
    assert c["provisional_total_votes"] == "" and c["early_combined_only"] is True
    assert c["method_sum_total_votes"] == 150
    assert n["itemized"] is False and n["eday_total_votes"] == ""
    assert s["fetched_at"] == "" and s["fetched_at_basis"] == ""  # none passed
    assert sum(r["votes"] for r in tidy) == sum(r["votes"] for r in LONG)


def test_fetched_at_passthrough():
    wide, tidy = vote_rows(REG, LONG, {"Split": ("2026-11-03 20:05:00 EST", "local run")})
    assert wide[0]["fetched_at"] == "2026-11-03 20:05:00 EST" and wide[0]["fetched_at_basis"] == "local run"
    assert wide[1]["fetched_at"] == "" and wide[2]["fetched_at"] == ""
    assert {r["fetched_at"] for r in tidy if r["county"] == "Split"} == {"2026-11-03 20:05:00 EST"}


def test_fetched_at_from_output_stamp(tmp_path):
    from tools.build_method_workbook import fetched_at
    d = tmp_path / "warren"
    (d / "output").mkdir(parents=True)
    for s in ("20261103_200500", "20261103_201000"):
        (d / "output" / f"summary_wide_{s}.csv").write_text("x")
    (d / "output" / "summary_wide_latest.csv").write_text("x")
    ts, basis = fetched_at(d, from_output=False)
    from datetime import datetime
    from tools.build_method_workbook import ET
    want = datetime(2026, 11, 3, 20, 10).astimezone().astimezone(ET)  # stamps use the machine's zone
    assert basis == "local run" and ts == want.strftime("%Y-%m-%d %H:%M:%S %Z")


# --- timing model (common/timing.py) ------------------------------------

def snap(t, county, votes, precincts, total=10):
    return [{"fetched_at": t, "county": county, "candidate": c, "votes": str(v),
             "precincts_reported": str(precincts), "precincts_total": str(total)} for c, v in votes.items()]


def test_timing_itemized_and_first_drop():
    from common.timing import first_drop, timing_rows
    reg = REG + [{"county": "Totals", "county_fips": "39007"}, {"county": "Late", "county_fips": "39009"}]
    snaps = (snap("t1", "Totals", {"Sherrod Brown": 0, "Jon Husted": 0}, 0)
             + snap("t2", "Totals", {"Sherrod Brown": 60, "Jon Husted": 40}, 0)      # absentee drop 1
             + snap("t3", "Totals", {"Sherrod Brown": 70, "Jon Husted": 50}, 0)      # absentee drop 2
             + snap("t4", "Totals", {"Sherrod Brown": 100, "Jon Husted": 130}, 6)    # precincts in
             + snap("t1", "Late", {"Sherrod Brown": 5, "Jon Husted": 9}, 2)          # first report had precincts
             + snap("t2", "Split", {"Sherrod Brown": 150, "Jon Husted": 25}, 0))     # first drop for a check
    rows = {r["county"]: r for r in timing_rows(reg, LONG, first_drop(snaps))}
    s = rows["Split"]
    assert s["timing_source"] == "itemized"
    assert s["pre_eday_dem_votes"] == 30 + 20 + 5  # evip + vbm + Post VBM (late mail is pre-Election Day)
    assert s["eday_total_votes"] == 194 and s["provisional_total_votes"] == 3
    assert s["has_mail_inperson_split"] is True
    assert s["first_drop_pre_eday_total_votes"] == 175 and s["first_drop_check_diff"] == 175 - s["pre_eday_total_votes"]
    c = rows["Combined"]
    assert c["pre_eday_total_votes"] == 40 and c["has_mail_inperson_split"] is False
    assert c["pre_eday_share_2way"] == round(40 / 150, 4)
    t = rows["Totals"]
    assert t["timing_source"] == "first_drop" and t["pre_eday_dem_votes"] == 70 and t["pre_eday_gop_votes"] == 50
    assert t["eday_dem_votes"] == 30 and t["eday_gop_votes"] == 80 and t["total_votes"] == 230
    assert t["provisional_total_votes"] == "" and t["precincts_reported"] == 6
    late = rows["Late"]
    assert late["timing_source"] == "none" and late["pre_eday_total_votes"] == "" and late["total_votes"] == 14
    assert rows["None"]["timing_source"] == "none" and "no statewide snapshot" in rows["None"]["notes"]


def test_snapshot_appends_only_changes(tmp_path):
    import csv
    from common.timing import append_snapshot, read_snapshots
    sw, log = tmp_path / "statewide.csv", tmp_path / "snaps.csv"
    def write(a_votes, b_votes, t):
        with sw.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["county", "candidate", "votes", "precincts_reported",
                                               "precincts_total", "write_in_detail", "fetched_at"])
            w.writeheader()
            for county, v in (("A", a_votes), ("B", b_votes)):
                w.writerow({"county": county, "candidate": "Sherrod Brown", "votes": v, "precincts_reported": 0,
                            "precincts_total": 5, "write_in_detail": "", "fetched_at": t})
    write(0, 0, "t1"); assert append_snapshot(sw, log) == 2
    write(0, 0, "t2"); assert append_snapshot(sw, log) == 0       # unchanged: nothing appended
    write(7, 0, "t3"); assert append_snapshot(sw, log) == 1       # only A changed
    assert [r["fetched_at"] for r in read_snapshots(log)] == ["t1", "t1", "t3"]


# --- Clermont link picker -----------------------------------------------

def test_clermont_pick():
    from counties.clermont.scraper import pick
    zero = ("https://boe.clermontcountyohio.gov/ZeroReport2026GEN.pdf?t=1", "Zero Report")
    old = [("https://boe.clermontcountyohio.gov/OfficialGroupDetail.pdf?t=2",
            "2026 May 5 Primary Election - Summary Group Detail - Official Results"),
           ("https://boe.clermontcountyohio.gov/2026%20Election%20Calendar.pdf", "2026 Election Calendar")]
    # Before results: only the zero report qualifies (May files and the calendar don't)
    assert pick([zero, *old]) == zero[0]
    night = [("https://boe.clermontcountyohio.gov/2026GEN Unofficial Precinct.pdf", "2026 November 3 - Precinct Report"),
             ("https://boe.clermontcountyohio.gov/2026GEN Unofficial Summary Group.pdf",
              "2026 November 3 - General Election - Summary Group Detail - Unofficial Results")]
    # Election night: the summary, never the precinct report or the zero report
    assert pick([zero, *old, *night]).endswith("Unofficial Summary Group.pdf")
    assert pick(old) is None


# --- Senate-only committed data -----------------------------------------

def test_save_senate_only(tmp_path):
    import csv
    from common.senate import save_senate_only
    src, dst = tmp_path / "latest.csv", tmp_path / "data.csv"
    cols = ["race", "contestant", "Election Day", "total"]
    def write(path, races):
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for race, who in races:
                w.writerow({"race": race, "contestant": who, "Election Day": 1, "total": 1})
    write(src, [("Governor", "A"), ("U.S. Senator", "Sherrod Brown"), ("U.S. Senator", "Jon Husted"),
                ("State Senator 7th District", "X")])  # a state senate race must not match
    assert save_senate_only(src, dst) == 2
    assert [r["contestant"] for r in csv.DictReader(dst.open())] == ["Sherrod Brown", "Jon Husted"]
    # A feed with no U.S. Senate race is refused and the good file is kept.
    write(src, [("Governor", "A")])
    try:
        save_senate_only(src, dst)
        raise AssertionError("expected a refusal")
    except RuntimeError:
        pass
    assert [r["contestant"] for r in csv.DictReader(dst.open())] == ["Sherrod Brown", "Jon Husted"]


def test_brown_husted_gate(tmp_path):
    import csv
    from common.senate import save_senate_only
    src, dst = tmp_path / "latest.csv", tmp_path / "data.csv"
    cols = ["race", "contestant", "party", "Election Day", "Mail", "total"]
    def write(rows):
        with src.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for who, ed, mail, tot, party in rows:
                w.writerow({"race": "U.S. Senator", "contestant": who, "party": party,
                            "Election Day": ed, "Mail": mail, "total": tot})
    def refused():
        try:
            save_senate_only(src, dst)
        except RuntimeError as e:
            return str(e)
        return ""
    good = [("Sherrod Brown", 5, 5, 10, ""), ("Jon Husted", 3, 4, 7, ""), ("Write-in", 1, 0, 1, "")]
    write(good)
    assert save_senate_only(src, dst) == 3
    # Party-prefixed names (Franklin) still count as Brown / Husted
    write([("Dem Sherrod Brown", 1, 1, 2, "Dem"), ("Rep Jon Husted", 1, 0, 1, "Rep")])
    assert save_senate_only(src, dst) == 2
    write(good)
    save_senate_only(src, dst)
    # Husted missing -> refused, last good file kept
    write([("Sherrod Brown", 5, 5, 10, "")])
    assert "missing Jon Husted" in refused()
    # Brown's vote types don't add up -> refused
    write([("Sherrod Brown", 5, 4, 10, ""), ("Jon Husted", 3, 4, 7, "")])
    assert "Sherrod Brown: vote types sum to 9" in refused()
    assert len(list(csv.DictReader(dst.open()))) == 3  # still the good file
    # A write-in mismatch only warns: saved
    write([("Sherrod Brown", 5, 5, 10, ""), ("Jon Husted", 3, 4, 7, ""), ("Write-in", 1, 1, 1, "")])
    assert save_senate_only(src, dst) == 3


# --- aggregator layout (tools/county_format.py) -------------------------

def test_county_format_math():
    from datetime import datetime
    from common.timing import timing_rows, first_drop
    from tools.build_method_workbook import vote_rows
    from tools.county_format import county_rows
    reg = [{"county": "Split", "county_fips": "39001"}, {"county": "Totals", "county_fips": "39007"},
           {"county": "None", "county_fips": "39005"}]
    wide, _ = vote_rows(reg, LONG)
    snaps = (snap("2026-11-03T23:40:00+00:00", "Totals", {"Sherrod Brown": 70, "Jon Husted": 50}, 0)
             + snap("2026-11-04T01:00:00+00:00", "Totals", {"Sherrod Brown": 100, "Jon Husted": 130}, 6))
    tim = timing_rows(reg, LONG, first_drop(snaps))
    statewide = {"Split": {"votes": {"dem": 157, "gop": 116, "breakout_2": 4, "other": 1},
                           "precincts_reported": "3", "precincts_total": "12", "fetched_at": "2026-11-04T01:00:00+00:00"},
                 "Totals": {"votes": {"dem": 100, "gop": 130}, "precincts_reported": "6", "precincts_total": "10",
                            "fetched_at": "2026-11-04T01:00:00+00:00"},
                 "None": {"votes": {}, "precincts_reported": "0", "precincts_total": "5",
                          "fetched_at": "2026-11-04T01:00:00+00:00"}}
    built = datetime(2026, 11, 3, 21, 0)
    rows = county_rows(reg, wide, tim, {"Split": ("2026-11-03 20:55:00 EST", "local run")}, statewide, built)
    st, n, s, t = rows  # Statewide first, then alphabetical: None, Split, Totals
    assert [r["reporting_unit_name"] for r in rows] == ["Statewide", "None County", "Split County", "Totals County"]
    # Split (itemized): Brown 100 eday + 30 evip + 20 vbm + 2 prov + 5 Post VBM = 157
    assert s["total_votes"] == 157 + 116 + 4 + 1 and s["dem_votes"] == 157 and s["gop_votes"] == 116
    assert s["dem_margin"] == 41 and s["two_way"] == round(157 / 273, 6)
    assert s["eday_total_votes"] == 194 and s["eday_dem_margin"] == 10
    assert s["early_dem_votes"] == 55  # evip 30 + vbm 20 + late mail 5
    assert s["evip_total_votes"] == 40 and s["vbm_gop_votes"] == 15 and s["provisional_total_votes"] == 3
    assert s["pct_eday"] == round(194 / 278, 6) and s["method_source"] == "itemized"
    assert s["precincts_total"] == "2" and "precincts from the SOS statewide site" not in s["notes"]  # feed has them
    assert s["latest_data_as_of"] == datetime(2026, 11, 3, 20, 55)
    # Totals (first-drop estimate): early 70/50, eday 30/80; no evip/vbm/provisional
    assert t["method_source"] == "first_drop" and t["early_dem_votes"] == 70 and t["eday_gop_votes"] == 80
    assert t["evip_total_votes"] == "" and t["provisional_total_votes"] == ""
    assert t["pct_precincts_in"] == 0.6 and t["reporting_status"] == "Reporting In Progress"
    assert n["reporting_status"] == "Not Started" and n["method_source"] == "totals_only"
    # Statewide row: toplines over all counties, precincts from the statewide site
    assert st["total_votes"] == 278 + 230 and st["precincts_total"] == 27 and st["pct_eday"] == ""
    assert st["eday_total_votes"] == 194 + 110
