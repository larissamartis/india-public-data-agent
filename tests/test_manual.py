from io import BytesIO

import duckdb
import httpx
import openpyxl
import pytest
import yaml

from bharat.ingest import manual, rbi
from bharat.ingest.common import make_client, sha256_bytes
from bharat.ingest.manifest import ManifestFile


def workbook(rows) -> bytes:
    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


GSDP = workbook(
    [
        ["Table 21: Gross State Domestic Product (Current Prices)"],
        ["(₹ Lakh)"],
        [],
        ["Sr. No.", "State", "2011-12", "2012-13", "2013-14 (P)"],
        [1, "Andhra Pradesh*", 37941000, "41,15,000", None],
        [2, "Goa", 4209800, 3812000, 4200000],
        [3, "Telangana", "-", "-", 45160000],
        [None, "All India", 8736329, 9944013, 11233522],
        ["Note: * Undivided Andhra Pradesh till 2013-14."],
        ["Source: National Statistical Office."],
    ]
)


def entry(name, content, **extra) -> ManifestFile:
    return ManifestFile(
        name=name,
        source="rbi",
        original_url=f"https://rbidocs.rbi.org.in/rdocs/Publications/DOCs/{name}",
        downloaded_on="2026-10-27",
        sha256=sha256_bytes(content),
        **extra,
    )


def release(files: dict[str, bytes]):
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        name = request.url.path.rsplit("/", 1)[-1]
        if name not in files:
            return httpx.Response(404)
        return httpx.Response(200, content=files[name])

    return make_client(transport=httpx.MockTransport(handler)), requested


def test_parse_state_by_year_unpivots_and_skips_notes():
    records = rbi.parse_state_by_year(GSDP)
    got = {(r["state_name"], r["fy"]): r["value"] for r in records}
    assert got[("Andhra Pradesh", "2012-13")] == 4115000
    assert got[("All India", "2013-14")] == 11233522
    assert ("Andhra Pradesh", "2013-14") not in got  # blank cell, no row
    assert ("Telangana", "2011-12") not in got  # '-' means no figure
    assert len(records) == 9


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2011-12", "2011-12"),
        ("2023 - 24 (P)", "2023-24"),
        ("1999-00", "1999-00"),
        ("2025-11", None),
        (2011, None),
        ("State", None),
    ],
)
def test_fy_label(raw, expected):
    assert rbi.fy_label(raw) == expected


def test_repeated_years_are_refused():
    content = workbook([["State", "2011-12", "2012-13", "2011-12"], ["Goa", 1, 2, 3]])
    with pytest.raises(rbi.RbiFormatError, match="more than one column"):
        rbi.parse_state_by_year(content)


def test_table_without_years_is_refused():
    with pytest.raises(rbi.RbiFormatError, match="year labels"):
        rbi.parse_state_by_year(workbook([["State", "Value"], ["Goa", 1]]))


def test_fetch_files_downloads_and_checks(tmp_path):
    client, requested = release({"t21.xlsx": GSDP})
    paths = manual.fetch_files([entry("t21.xlsx", GSDP)], tmp_path, client=client, repo="me/r")
    assert paths[0].read_bytes() == GSDP
    assert requested == ["/me/r/releases/download/raw-inputs/t21.xlsx"]
    manual.fetch_files([entry("t21.xlsx", GSDP)], tmp_path, client=client, repo="me/r")
    assert len(requested) == 1  # already present, not downloaded again


def test_fetch_files_refuses_a_changed_file(tmp_path):
    client, _ = release({"t21.xlsx": GSDP + b"edited"})
    with pytest.raises(manual.ManualFileError, match="hash differs"):
        manual.fetch_files([entry("t21.xlsx", GSDP)], tmp_path, client=client)


def test_fetch_files_names_a_missing_upload(tmp_path):
    client, _ = release({})
    with pytest.raises(manual.ManualFileError, match="not on the raw-inputs release"):
        manual.fetch_files([entry("t21.xlsx", GSDP)], tmp_path, client=client)


def test_inspect_shows_the_first_rows(tmp_path):
    path = tmp_path / "t21.xlsx"
    path.write_bytes(GSDP)
    text = manual.inspect_file(path)
    assert "Sr. No. | State | 2011-12 | 2012-13 | 2013-14 (P)" in text
    assert "[sheet Sheet:" in text
    (tmp_path / "x.csv").write_text("State,Volume\nGoa,12\n", encoding="utf-8")
    assert "State | Volume" in manual.inspect_file(tmp_path / "x.csv")
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    assert "could not read" in manual.inspect_file(tmp_path / "bad.pdf")


def test_rbi_run_writes_bronze(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.yml"
    item = entry("t21.xlsx", GSDP, dataset="gsdp_current", unit="₹ lakh")
    manifest.write_text(
        yaml.safe_dump({"files": [item.model_dump(mode="json", exclude_none=True)]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rbi, "entries_for", lambda s: manual.entries_for(s, manifest))
    client, _ = release({"t21.xlsx": GSDP})
    [path] = rbi.run(tmp_path, client=client)
    got = duckdb.sql(
        f"select dataset, unit, count(*), count(distinct state_name) from '{path.as_posix()}' "
        "group by all"
    ).fetchall()
    assert got == [("gsdp_current", "₹ lakh", 9, 4)]


def test_rbi_run_needs_dataset_and_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(rbi, "entries_for", lambda s: [entry("t21.xlsx", GSDP)])
    client, _ = release({"t21.xlsx": GSDP})
    with pytest.raises(rbi.RbiFormatError, match="dataset"):
        rbi.run(tmp_path, client=client)
