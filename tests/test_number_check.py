from bharat.agent.number_check import extract_numbers, unsupported_numbers


def test_extract_skips_fy_labels_and_reads_scales():
    found = extract_numbers("Kerala grew 12.3% in 2023-24, reaching ₹4.2 lakh crore.")
    assert [m.text for m in found] == ["12.3", "4.2 lakh crore"]
    assert found[1].scale == 1e12


def test_number_not_in_result_is_flagged():
    answer = "Kerala's CPI was 195.2 and Goa's was 201.7."
    assert unsupported_numbers(answer, [195.24, 190.0]) == ["201.7"]


def test_rounded_values_are_accepted():
    assert unsupported_numbers("Unemployment was 4.1%.", [4.137]) == []
    assert unsupported_numbers("Unemployment was 4%.", [4.137]) == []


def test_lakh_crore_matches_value_stored_in_crore():
    assert unsupported_numbers("GSDP was ₹4.2 lakh crore.", [418_000.0]) == []


def test_indian_digit_grouping():
    assert unsupported_numbers("1,23,456 transactions", [123_456]) == []


def test_allowed_extras_and_years():
    answer = "In 2025, the top 5 states averaged 7.5%."
    assert unsupported_numbers(answer, [7.5]) == ["5"]
    assert unsupported_numbers(answer, [7.5], allowed=[5]) == []


def test_falls_are_matched_by_size():
    assert unsupported_numbers("It fell by 2.5 points.", [-2.5]) == []


def test_dates_are_ignored():
    assert unsupported_numbers("As of 26 Oct 2026, the index was 7.5.", [7.5]) == []
