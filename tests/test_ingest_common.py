from datetime import date

import duckdb
import httpx
import pytest

from bharat.contracts import Contract, ContractError
from bharat.ingest.bronze import save_bronze
from bharat.ingest.common import make_client, request_with_retry, sha256_bytes, to_float
from bharat.ingest.manifest import Manifest, verify_files


def test_retry_waits_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) < 3 else 200, text="ok")

    waits = []
    client = make_client(transport=httpx.MockTransport(handler))
    response = request_with_retry(client, "GET", "https://example.test/x", sleep=waits.append)
    assert response.status_code == 200
    assert len(calls) == 3
    assert waits == [2.0, 4.0]
    assert "india-public-data-agent" in calls[0].headers["User-Agent"]


def test_retry_returns_non_retryable_errors_untouched():
    client = make_client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    response = request_with_retry(client, "GET", "https://example.test/x", sleep=lambda s: None)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,23,456.5", 123456.5), (12, 12.0), ("-", None), ("", None), (None, None), ("nan", None)],
)
def test_to_float(raw, expected):
    assert to_float(raw) == expected


CONTRACT = Contract.model_validate(
    {
        "source": "test",
        "table": "demo",
        "key": ["state", "month"],
        "columns": {
            "state": {"type": "VARCHAR", "not_null": True, "state_name": True},
            "month": {"type": "DATE", "not_null": True},
            "value": {"type": "DOUBLE", "min": 0},
        },
    }
)
COLUMNS = {"state": "VARCHAR", "month": "DATE", "value": "DOUBLE"}


def test_save_bronze_writes_parquet_with_load_columns(tmp_path):
    rows = [
        {"state": "Kerala", "month": "2026-08-01", "value": 1.5, "_source_ref": "file.xlsx"},
        {"state": "Goa", "month": date(2026, 8, 1), "value": None, "_source_ref": "file.xlsx"},
    ]
    path = save_bronze(rows, COLUMNS, CONTRACT, tmp_path)
    got = duckdb.sql(
        f"select state, month, value, _source_ref, _retrieved_at from '{path.as_posix()}' "
        "order by state"
    ).fetchall()
    assert [(r[0], r[1], r[2], r[3]) for r in got] == [
        ("Goa", date(2026, 8, 1), None, "file.xlsx"),
        ("Kerala", date(2026, 8, 1), 1.5, "file.xlsx"),
    ]
    assert got[0][4] is not None


def test_save_bronze_refuses_rows_that_break_the_contract(tmp_path):
    rows = [{"state": "Atlantis", "month": "2026-08-01", "value": -1, "_source_ref": "f"}]
    with pytest.raises(ContractError, match="Atlantis"):
        save_bronze(rows, COLUMNS, CONTRACT, tmp_path)
    assert not (tmp_path / "bronze" / "demo.parquet").exists()


def test_manifest_verification(tmp_path):
    good = tmp_path / "a.xlsx"
    good.write_bytes(b"alpha")
    changed = tmp_path / "b.xlsx"
    changed.write_bytes(b"beta-edited")
    (tmp_path / "stray.pdf").write_bytes(b"x")
    manifest = Manifest.model_validate(
        {
            "files": [
                {
                    "name": name,
                    "source": "rbi_handbook",
                    "original_url": "https://example.test/" + name,
                    "downloaded_on": "2026-10-27",
                    "sha256": sha256_bytes(content),
                }
                for name, content in [("a.xlsx", b"alpha"), ("b.xlsx", b"beta"), ("c.xlsx", b"c")]
            ]
        }
    )
    assert verify_files(manifest, tmp_path) == [
        "changed (hash differs from manifest): b.xlsx",
        "missing: c.xlsx",
        "not in manifest: stray.pdf",
    ]
