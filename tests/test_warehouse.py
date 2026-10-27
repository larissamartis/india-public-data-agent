import json

import duckdb

from bharat.warehouse import __main__ as cli
from bharat.warehouse.fixtures import write_fixtures
from bharat.warehouse.prepare import BRONZE_TABLES, prepare


def test_prepare_fills_missing_tables_and_maps_every_name(tmp_path):
    write_fixtures(tmp_path)
    counts = prepare(tmp_path)
    assert all((tmp_path / f"{t}.parquet").exists() for t in BRONZE_TABLES)
    assert counts["missing_tables"] == len(BRONZE_TABLES) - 4
    names = dict(
        duckdb.sql(f"select * from '{(tmp_path / 'ref_state_name.parquet').as_posix()}'").fetchall()
    )
    assert names["ALL INDIA"] == 0
    assert names["India"] == 0
    assert names["Dadra & Nagar Haveli"] == 26
    assert names["KERALA"] == 32
    states = duckdb.sql(f"select count(*) from '{(tmp_path / 'ref_state.parquet').as_posix()}'")
    assert states.fetchall()[0][0] == 39  # 38 LGD entries plus India


def test_empty_table_keeps_contract_columns(tmp_path):
    prepare(tmp_path)
    columns = [
        row[0]
        for row in duckdb.sql(
            f"describe select * from '{(tmp_path / 'mospi_cpi.parquet').as_posix()}'"
        ).fetchall()
    ]
    assert "state" in columns and "_source_ref" in columns


def test_report_posts_failures(tmp_path, monkeypatch, capsys):
    results = tmp_path / "run_results.json"
    results.write_text(
        json.dumps(
            {
                "results": [
                    {"status": "success", "unique_id": "model.x.a", "message": "OK"},
                    {"status": "fail", "unique_id": "test.x.unique_b", "message": "Got 2 results"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cli.report(results) == 1
    out = capsys.readouterr().out
    assert "::error title=dbt fail: test.x.unique_b::Got 2 results" in out
    assert "1 passed, 0 warned, 1 failed" in out


def test_previous_values_are_kept_and_the_old_database_removed(tmp_path):
    from bharat.warehouse.prepare import save_previous_values

    database = tmp_path / "serving.duckdb"
    con = duckdb.connect(str(database))
    con.execute(
        "create table fct_state_metric as select 'gst_total|32|2026-08' as row_key, "
        "'gst_total' as metric_id, '2026-08' as period_label, 2500.0 as value"
    )
    con.execute("create table build_info as select timestamp '2026-10-27 10:00' as built_at")
    con.close()
    assert save_previous_values(database, tmp_path) == 1
    assert not database.exists()
    rows = duckdb.sql(f"select * from '{(tmp_path / 'previous_values.parquet').as_posix()}'")
    assert rows.fetchall()[0][:4] == ("gst_total|32|2026-08", "gst_total", "2026-08", 2500.0)


def test_first_build_has_no_previous_values(tmp_path):
    from bharat.warehouse.prepare import save_previous_values

    assert save_previous_values(tmp_path / "none.duckdb", tmp_path) == 0
    assert (tmp_path / "previous_values.parquet").exists()


def test_report_shows_dbt_log_errors_when_dbt_never_ran(tmp_path, monkeypatch, capsys):
    log = tmp_path / "dbt.log"
    log.write_text("info line\nCompilation Error in metric x\n  bad filter\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cli.report(tmp_path / "missing.json", log) == 1
    assert "Compilation Error in metric x" in capsys.readouterr().out
