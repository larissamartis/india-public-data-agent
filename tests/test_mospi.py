import json
from datetime import date
from urllib.parse import parse_qs

import duckdb
import httpx
import pytest

from bharat.ingest import mospi
from bharat.ingest.common import make_client


def cpi_row(state, month, value):
    return {
        "baseyear": "2012",
        "year": "2025",
        "month": month,
        "state": state,
        "sector": "Combined",
        "group": "General",
        "subgroup": "",
        "index": str(value),
        "inflation": "3.1",
        "status": "F",
    }


class FakeMospi:
    """Pretend API: two pages of CPI rows, and tokens that can be expired on demand."""

    def __init__(self):
        self.logins = 0
        self.valid_token = None
        self.expire_next = False
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/login":
            self.logins += 1
            assert json.loads(request.content)["email"] == "me@example.test"
            self.valid_token = f"tok{self.logins}"
            return httpx.Response(
                200, json={"statusCode": 200, "response": {"token": self.valid_token}}
            )
        self.requests.append(request)
        if self.expire_next or request.headers.get("Authorization") != self.valid_token:
            self.expire_next = False
            return httpx.Response(401, json={"msg": "token expired"})
        params = parse_qs(request.url.query.decode())
        assert params["Format"] == ["JSON"]
        if params.get("year") == ["2026"]:
            return httpx.Response(404, json={"msg": "No Data Found"})
        page = int(params["page"][0])
        rows = (
            [cpi_row("Kerala", "January", 190.5), cpi_row("Goa", "January", 188.0)]
            if page == 1
            else [cpi_row("All India", "January", 192.0)]
        )
        return httpx.Response(
            200,
            json={
                "data": rows,
                "meta_data": {"page": page, "totalPages": 2, "recordPerPage": 2},
                "msg": "Data fetched",
            },
        )


def make(fake, clock=None):
    http = make_client(transport=httpx.MockTransport(fake))
    return mospi.MospiClient(
        "me@example.test", "pw", http, sleep=lambda s: None, clock=clock or (lambda: 0.0)
    )


def test_fetch_all_walks_pages_and_logs_in_once():
    fake = FakeMospi()
    client = make(fake)
    rows = client.fetch_all("/api/cpi/getCPIIndex", {"year": "2025"})
    assert [r["state"] for r in rows] == ["Kerala", "Goa", "All India"]
    assert fake.logins == 1


def test_expired_token_triggers_one_new_login():
    fake = FakeMospi()
    client = make(fake)
    client.fetch_all("/api/cpi/getCPIIndex", {"year": "2025"})
    fake.expire_next = True
    rows = client.fetch_all("/api/cpi/getCPIIndex", {"year": "2025"})
    assert len(rows) == 3
    assert fake.logins == 2


def test_token_is_refreshed_before_15_minutes():
    fake = FakeMospi()
    now = [0.0]
    client = make(fake, clock=lambda: now[0])
    client.fetch_all("/api/cpi/getCPIIndex", {"year": "2025"})
    now[0] = 15 * 60
    client.fetch_all("/api/cpi/getCPIIndex", {"year": "2025"})
    assert fake.logins == 2


def test_no_data_is_an_empty_result():
    client = make(FakeMospi())
    assert client.fetch_all("/api/cpi/getCPIIndex", {"year": "2026"}) == []


def test_missing_field_names_what_arrived():
    with pytest.raises(mospi.MospiError, match="baseyear"):
        mospi.CPI.convert({"year": "2025"}, "ref")


def test_run_writes_cpi_bronze(tmp_path):
    client = make(FakeMospi())
    queries = [{"base_year": "2012", "series": "Current", "year": "2025", "group_code": "8"}]
    dataset = mospi.Dataset(
        name="mospi_cpi", path=mospi.CPI.path, fields=mospi.CPI.fields, queries=lambda t: queries
    )
    mospi.DATASETS["mospi_cpi_test"] = dataset
    try:
        path = mospi.run("mospi_cpi_test", tmp_path, client=client, today=date(2026, 1, 15))
    finally:
        del mospi.DATASETS["mospi_cpi_test"]
    got = duckdb.sql(
        f"select state, index_value, _source_ref from '{path.as_posix()}' order by state"
    ).fetchall()
    assert [(s, v) for s, v, _ in got] == [("All India", 192.0), ("Goa", 188.0), ("Kerala", 190.5)]
    assert got[0][2].startswith("https://api.mospi.gov.in/api/cpi/getCPIIndex?")


def test_query_plans_cover_the_agreed_years():
    today = date(2026, 10, 26)
    cpi = mospi.CPI.queries(today)
    assert {q["year"] for q in cpi} == {str(y) for y in range(2013, 2027)}
    plfs = mospi.PLFS.queries(today)
    assert {"2017-18", "2023-24", "2022", "2026"} <= {q["year"] for q in plfs}
    assert all("frequency_code" not in q for q in plfs if "-" in q["year"])
    asi = mospi.ASI.queries(today)
    assert {q["year"] for q in asi} >= {"2008-09", "2023-24"}
