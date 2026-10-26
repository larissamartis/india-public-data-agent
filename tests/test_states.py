from datetime import date

import pytest

from bharat.reference.states import (
    StateDateError,
    UnknownStateError,
    load_states,
    normalise_name,
    resolve_state,
)


def test_list_has_36_current_entities_and_unique_codes():
    states = load_states()
    codes = [s.code for s in states]
    assert len(codes) == len(set(codes))
    today = date(2026, 10, 26)
    assert sum(s.exists_on(today) for s in states) == 36


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Jammu & Kashmir", "jammu and kashmir"),
        ("  NCT of Delhi* ", "nct of delhi"),
        ("The Andaman & Nicobar Islands", "andaman and nicobar islands"),
    ],
)
def test_normalise_name(raw, expected):
    assert normalise_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("Orissa", 21),
        ("ODISHA", 21),
        ("J&K", 1),
        ("Pondicherry", 34),
        ("Uttaranchal", 5),
        ("Dadra & Nagar Haveli and Daman & Diu", 38),
        ("Andaman & Nicobar Islands", 35),
        ("Telengana", 36),
    ],
)
def test_resolve_known_variants(raw, code):
    assert resolve_state(raw).code == code


def test_unknown_name_fails():
    with pytest.raises(UnknownStateError):
        resolve_state("North East")


def test_state_that_did_not_exist_yet_fails():
    with pytest.raises(StateDateError):
        resolve_state("Telangana", on=date(2010, 3, 31))
    assert resolve_state("Telangana", on=date(2014, 6, 2)).code == 36


def test_merged_uts_stop_existing():
    with pytest.raises(StateDateError):
        resolve_state("Daman and Diu", on=date(2021, 3, 31))
    assert resolve_state("Daman and Diu", on=date(2020, 1, 25)).code == 25
