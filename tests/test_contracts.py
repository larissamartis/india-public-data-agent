from datetime import date

import duckdb
import pytest

from bharat.contracts import (
    Contract,
    ContractError,
    check_contract,
    enforce_contract,
    load_contract,
)

TODAY = date(2026, 10, 26)

CONTRACT = {
    "source": "test_cpi",
    "table": "cpi",
    "key": ["state", "month", "sector"],
    "columns": {
        "state": {"type": "VARCHAR", "not_null": True, "state_name": True},
        "month": {"type": "DATE", "not_null": True},
        "sector": {"type": "VARCHAR", "allowed": ["Rural", "Urban", "Combined"]},
        "index_value": {"type": "DOUBLE", "min": 0, "max": 1000},
    },
    "freshness": {"column": "month", "max_age_days": 120},
}


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("create table cpi (state varchar, month date, sector varchar, index_value double)")
    con.execute(
        """
        insert into cpi values
          ('Kerala', date '2026-08-01', 'Rural', 195.2),
          ('Kerala', date '2026-08-01', 'Urban', 190.4),
          ('Orissa', date '2026-08-01', 'Combined', 188.0)
        """
    )
    return con


def rules(violations):
    return {(v.rule, v.column) for v in violations}


def test_good_table_passes(con):
    assert check_contract(con, Contract.model_validate(CONTRACT), today=TODAY) == []


def test_missing_table(con):
    contract = Contract.model_validate({**CONTRACT, "table": "nope"})
    assert rules(check_contract(con, contract, today=TODAY)) == {("table_exists", None)}


def test_schema_drift_is_caught(con):
    con.execute("alter table cpi add column note varchar")
    con.execute("alter table cpi alter index_value type varchar")
    found = rules(check_contract(con, Contract.model_validate(CONTRACT), today=TODAY))
    assert ("unexpected_column", "note") in found
    assert ("column_type", "index_value") in found


def test_value_rules(con):
    con.execute(
        """
        insert into cpi values
          ('Atlantis', date '2026-08-01', 'Rural', 10),
          ('Goa', date '2026-08-01', 'Semi-urban', -5),
          ('Goa', null, 'Rural', 5000)
        """
    )
    found = rules(check_contract(con, Contract.model_validate(CONTRACT), today=TODAY))
    assert {
        ("state_name", "state"),
        ("allowed", "sector"),
        ("min", "index_value"),
        ("max", "index_value"),
        ("not_null", "month"),
    } <= found


def test_duplicate_key(con):
    con.execute("insert into cpi values ('Kerala', date '2026-08-01', 'Rural', 196.0)")
    assert ("unique_key", None) in rules(
        check_contract(con, Contract.model_validate(CONTRACT), today=TODAY)
    )


def test_row_count_drift(con):
    contract = Contract.model_validate(CONTRACT)
    assert check_contract(con, contract, previous_row_count=3, today=TODAY) == []
    assert ("row_count", None) in rules(
        check_contract(con, contract, previous_row_count=10, today=TODAY)
    )


def test_stale_data(con):
    late = date(2027, 6, 1)
    assert ("freshness", "month") in rules(
        check_contract(con, Contract.model_validate(CONTRACT), today=late)
    )


def test_enforce_raises_with_readable_message(con):
    con.execute("delete from cpi")
    with pytest.raises(ContractError, match="table is empty"):
        enforce_contract(con, Contract.model_validate(CONTRACT), today=TODAY)


def test_load_contract_from_yaml(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text(
        "source: s\ntable: t\ncolumns:\n  a: {type: INTEGER, not_null: true}\n", encoding="utf-8"
    )
    contract = load_contract(path)
    assert contract.columns["a"].not_null is True


def test_contract_rejects_unknown_rule_names():
    with pytest.raises(ValueError):
        Contract.model_validate({**CONTRACT, "colums": {}})
