from bharat.contracts import ContractError, Violation
from bharat.ingest import __main__ as cli


def test_cli_prints_summary_and_notice(tmp_path, monkeypatch, capsys):
    import duckdb

    path = tmp_path / "bronze" / "demo.parquet"
    path.parent.mkdir(parents=True)
    duckdb.sql(
        "select * from (values ('Kerala', date '2026-01-01'), ('Goa', date '2026-02-01')) "
        "t(state_name, month)"
    ).write_parquet(path.as_posix())
    monkeypatch.setitem(cli.SOURCES, "gst", lambda out: [path])
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert cli.main(["gst", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "demo.parquet: 2 rows; 2 distinct state_name; month 2026-01-01 to 2026-02-01" in out
    assert "::notice title=gst loaded::" in out


def test_cli_reports_contract_failures(monkeypatch, capsys):
    def fail(out):
        raise ContractError("gst", [Violation("state_name", "state_name", "unmatched ['X']")])

    monkeypatch.setitem(cli.SOURCES, "gst", fail)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cli.main(["gst"]) == 1
    assert "::error title=gst contract::" in capsys.readouterr().out


def test_cli_previews_sources_without_a_parser(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "_inspect", lambda source, out, pages: ["npci.xlsx (10 bytes)\nState | Volume"]
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cli.main(["npci"]) == 0
    out = capsys.readouterr().out
    assert "no parser yet" in out
    assert "::notice title=npci preview::npci.xlsx (10 bytes)%0AState | Volume" in out


def test_cli_refuses_inspect_for_scripted_sources(capsys):
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["gst", "--inspect"])
