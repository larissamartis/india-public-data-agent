import pytest

from bharat.agent.sql_guard import check_sql

ALLOWED = {"fct_state_metric", "dim_state", "dim_metric"}


def test_plain_select_is_allowed_and_capped():
    result = check_sql("select state_code, value from fct_state_metric", ALLOWED)
    assert result.ok, result.errors
    assert "LIMIT 1000" in result.sql
    assert result.tables == ("fct_state_metric",)


def test_small_limit_is_kept():
    result = check_sql("select * from dim_state limit 5", ALLOWED)
    assert result.ok
    assert "LIMIT 5" in result.sql
    assert "LIMIT 1000" not in result.sql


def test_large_limit_is_capped():
    result = check_sql("select * from dim_state limit 50000", ALLOWED)
    assert result.ok
    assert "LIMIT 1000" in result.sql
    assert "50000" not in result.sql


def test_ctes_and_joins_are_allowed():
    sql = """
        with m as (select * from fct_state_metric where metric_id = 'upi_volume')
        select s.state_name, m.value
        from m join dim_state s using (state_code)
        order by m.value desc
    """
    result = check_sql(sql, ALLOWED)
    assert result.ok, result.errors
    assert result.tables == ("dim_state", "fct_state_metric")


def test_union_is_wrapped_with_cap():
    result = check_sql(
        "select state_code from dim_state union all select state_code from fct_state_metric",
        ALLOWED,
    )
    assert result.ok, result.errors
    assert "LIMIT 1000" in result.sql


def test_table_names_are_case_insensitive():
    assert check_sql("SELECT * FROM FCT_STATE_METRIC", ALLOWED).ok


@pytest.mark.parametrize(
    "sql",
    [
        "select * from raw_secrets",
        "select * from information_schema.tables",
        "select * from read_csv('/etc/passwd')",
        "select * from '/etc/passwd'",
        "select getenv('HOME') from dim_state",
        "select * from dim_state; drop table dim_state",
        "delete from fct_state_metric",
        "drop table dim_state",
        "attach 'other.db'",
        "copy (select 1) to 'out.csv'",
        "insert into dim_state values (99, 'X')",
        "",
    ],
)
def test_unsafe_or_invalid_sql_is_rejected(sql):
    result = check_sql(sql, ALLOWED)
    assert not result.ok
    assert result.sql is None
    assert result.errors
