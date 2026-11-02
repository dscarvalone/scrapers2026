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
    assert sum(r["votes"] for r in tidy) == sum(r["votes"] for r in LONG)
