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
