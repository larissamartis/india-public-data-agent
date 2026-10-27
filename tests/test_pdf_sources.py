from datetime import date

import pytest

from bharat.ingest import population, trai


def word(text, centre, top):
    half = 2.5 * len(text)
    return {"text": text, "x0": centre - half, "x1": centre + half, "top": top, "bottom": top + 8}


COLS = [60, 100, 140, 200, 240, 280, 340, 380, 420]


def table_page(
    rows,
    names=(("INDIA",), ("JAMMU", "&", "KASHMIR", "(UT)"), ("HIMACHAL", "PRADESH")),
    offset_middle=0.0,
):
    """A Table 11 page as pdfplumber words. `rows` maps year -> 9 numbers.

    `offset_middle` drops the middle area's numbers lower on the line, as on the real page 86,
    where plain text extraction moves them after the right-hand area's numbers.
    """
    words = [word("TABLE", 200, 5), word("–", 230, 5), word("11", 245, 5)]
    words += [word("Projected", 120, 15), word("Total", 160, 15), word("('000)", 400, 15)]
    for group, parts in enumerate(names):
        centre = sum(COLS[3 * group : 3 * group + 3]) / 3
        for i, part in enumerate(parts):
            words.append(word(part, centre - 20 + 15 * i, 30))
    words.append(word("Year", 15, 40))
    for i, col in enumerate(COLS):
        words.append(word(["Persons", "Male", "Females"][i % 3], col, 50))
    words.append(word("1", 15, 60))
    words += [word(str(n), col, 60) for n, col in zip(range(2, 11), COLS, strict=True)]
    for r, (year, numbers) in enumerate(rows.items()):
        top = 75 + 12 * r
        words.append(word(str(year), 15, top))
        for i, (n, col) in enumerate(zip(numbers, COLS, strict=True)):
            words.append(word(f"{n:,}", col, top + (offset_middle if 3 <= i < 6 else 0)))
    words.append(word("82", 240, 75 + 12 * len(rows) + 40))  # page number
    return words


ROWS = {
    2011: [1216147, 625942, 590205, 12309, 6504, 5805, 6884, 3492, 3392],
    2012: [1232023, 633957, 598066, 12435, 6565, 5870, 6943, 3522, 3421],
}


def test_population_page_is_read_by_position():
    records = population.parse_table_page(table_page(ROWS, offset_middle=4.0))
    got = {(r["state_name"], r["year"]): r["persons_thousand"] for r in records}
    assert got[("JAMMU & KASHMIR", 2011)] == 12309  # not swapped with Himachal
    assert got[("HIMACHAL PRADESH", 2011)] == 6884
    assert got[("India", 2012)] == 1232023
    assert len(records) == 6
    assert {r["name_as_printed"] for r in records} >= {"JAMMU & KASHMIR (UT)"}


def test_population_page_without_unit_line_still_reads_names():
    words = [w for w in table_page(ROWS) if w["text"] != "('000)"]
    names = {r["name_as_printed"] for r in population.parse_table_page(words)}
    assert names == {"INDIA", "JAMMU & KASHMIR (UT)", "HIMACHAL PRADESH"}


def test_population_wrapped_title_is_not_read_as_a_name():
    words = table_page(ROWS)
    words += [word("Territories*", 70, 22), word("(’000)", 130, 22)]  # odd quote mark
    names = {r["name_as_printed"] for r in population.parse_table_page(words)}
    assert names == {"INDIA", "JAMMU & KASHMIR (UT)", "HIMACHAL PRADESH"}


def test_population_persons_must_equal_male_plus_female():
    bad = {2011: [1216147, 625942, 590205, 12309, 6504, 9999, 6884, 3492, 3392], 2012: ROWS[2012]}
    with pytest.raises(population.PopulationFormatError, match="is not male"):
        population.parse_table_page(table_page(bad))


def test_population_missing_number_is_refused():
    words = [w for w in table_page(ROWS) if w["text"] != "5,870"]
    with pytest.raises(population.PopulationFormatError, match="missing"):
        population.parse_table_page(words)


def test_population_totals_must_reach_india():
    records = [
        {"year": 2011, "state_name": "India", "persons_thousand": 1000},
        {"year": 2011, "state_name": "Goa", "persons_thousand": 600},
        {"year": 2011, "state_name": "Kerala", "persons_thousand": 395},
    ]
    assert population.check_totals(records) == []
    records[2]["persons_thousand"] = 300
    assert population.check_totals(records) == ["2011: states add to 900, India is 1,000"]


def test_population_clean_name():
    assert population.clean_name("JAMMU & KASHMIR (UT)") == "JAMMU & KASHMIR"
    assert population.clean_name("INDIA") == "India"


ANNEXURE_II = """RP-2/9/(4)/2025-NSL-II I/45442/2026
Wireless (Mobile) Subscriber Base Annexure-II
Bharti Airtel R e liance Com. Vodafone Idea BSNL MTNL Reliance Jio Total
Service Area Net Addition
{months}
{rows}
Total {total_before:,} {total_after:,} {total_net}
19
"""
NAMES = [
    "Andhra Pradesh",
    "Assam",
    "Bihar",
    "Delhi",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "J & K",
    "Karnataka",
    "Kerala",
    "Kolkata",
    "Madhya Pradesh",
    "Maharashtra",
    "Mumbai",
    "North East",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Tamil Nadu",
    "U.P.(E)",
    "U.P. (W)",
    "West Bengal",
]


def money(n):
    """TRAI prints negative numbers in brackets: (2,000)."""
    return f"({-n:,})" if n < 0 else f"{n:,}"


def annexure(net_for_assam=500):
    lines, before_sum, after_sum = [], 0, 0
    for i, name in enumerate(NAMES):
        before = 1_000_000 * (i + 1)
        net = net_for_assam if name == "Assam" else 1000 if i % 2 else -2000
        after = before + net
        lines.append(f"{name} 7,069,179 7,112,374 0 0 {before:,} {after:,} {money(net)}")
        before_sum += before
        after_sum += after
    return ANNEXURE_II.format(
        months=" ".join(["Aug-26 Sept-26"] * 7),
        rows="\n".join(lines),
        total_before=before_sum,
        total_after=after_sum,
        total_net=money(after_sum - before_sum),
    )


def test_trai_annexure_ii_reads_totals_for_both_months():
    records = trai.parse_annexure_ii(annexure())
    assert len(records) == 44
    got = {(r["service_area"], r["as_of"]): r["wireless_subscribers"] for r in records}
    assert got[("Jammu & Kashmir", date(2026, 8, 31))] == 8_000_000
    assert got[("UP (West)", date(2026, 9, 30))] == 21_000_000 - 2000
    assert got[("Andhra Pradesh", date(2026, 9, 30))] == 1_000_000 - 2000  # (2,000) is negative


def test_trai_net_addition_must_match():
    text = annexure().replace("2,000,000 2,000,500 500", "2,000,000 2,000,500 900")
    with pytest.raises(trai.TraiFormatError, match="Assam"):
        trai.parse_annexure_ii(text)


def test_trai_unknown_area_is_refused():
    with pytest.raises(trai.TraiFormatError, match="unknown service area 'Gondwana'"):
        trai.parse_annexure_ii(annexure().replace("Kolkata", "Gondwana"))


def test_trai_finds_the_annexure_page():
    pages = ["Annexure-I wireline", annexure(), "Annexure-III VLR"]
    assert trai.find_annexure_ii(pages) == pages[1]
    with pytest.raises(trai.TraiFormatError):
        trai.find_annexure_ii(pages[:1])


@pytest.mark.parametrize(
    ("label", "expected"), [("Sept-26", date(2026, 9, 30)), ("Feb-28", date(2028, 2, 29))]
)
def test_month_end(label, expected):
    assert trai.month_end(label) == expected
