"""MoSPI's official API (api.mospi.gov.in): CPI, PLFS and ASI by state.

Login gives a token that the manual says lasts 15 minutes, so the client logs in again after
14 minutes or on any 401. Results come in pages; the client walks them with a pause between
calls. Field names are mapped explicitly, and a missing field stops the run with the fields
that did arrive, so a change on MoSPI's side is caught on the first call.

Each source uses its own state codes, so only state names are kept for matching.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import httpx

from bharat.contracts import load_source_contract
from bharat.ingest.bronze import save_bronze
from bharat.ingest.common import make_client, request_with_retry, to_float

log = logging.getLogger(__name__)

BASE_URL = "https://api.mospi.gov.in"
TOKEN_LIFETIME_S = 14 * 60


class MospiError(RuntimeError):
    pass


def _find_token(body: object) -> str | None:
    if isinstance(body, dict):
        for key, value in body.items():
            if "token" in str(key).lower() and isinstance(value, str) and value:
                return value
        for value in body.values():
            found = _find_token(value)
            if found:
                return found
    elif isinstance(body, list):
        for value in body:
            found = _find_token(value)
            if found:
                return found
    return None


def _find_rows(body: object) -> list[dict]:
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if isinstance(body, dict):
        for key in ("data", "Data", "result", "records"):
            if isinstance(body.get(key), list):
                return [r for r in body[key] if isinstance(r, dict)]
        for value in body.values():
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                return value
    return []


def _total_pages(body: object) -> int | None:
    meta = body.get("meta_data") if isinstance(body, dict) else None
    if isinstance(meta, dict):
        try:
            return int(meta["totalPages"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


class MospiClient:
    def __init__(
        self,
        email: str,
        password: str,
        http: httpx.Client | None = None,
        *,
        delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_pages: int = 5000,
    ):
        self.email = email
        self.password = password
        self.http = http or make_client()
        self.delay = delay
        self.sleep = sleep
        self.clock = clock
        self.max_pages = max_pages
        self._token: str | None = None
        self._token_at = 0.0

    def login(self) -> None:
        response = request_with_retry(
            self.http,
            "POST",
            f"{BASE_URL}/api/login",
            json={"email": self.email, "password": self.password},
            sleep=self.sleep,
        )
        if response.status_code >= 400:
            raise MospiError(f"login failed: HTTP {response.status_code}")
        token = _find_token(response.json())
        if not token:
            raise MospiError("login reply had no token")
        self._token, self._token_at = token, self.clock()
        log.info("logged in to MoSPI API")

    def _headers(self) -> dict[str, str]:
        if self._token is None or self.clock() - self._token_at > TOKEN_LIFETIME_S:
            self.login()
        return {"Authorization": self._token}

    def _get(self, path: str, params: dict) -> httpx.Response:
        url = f"{BASE_URL}{path}"
        response = request_with_retry(
            self.http, "GET", url, params=params, headers=self._headers(), sleep=self.sleep
        )
        if response.status_code == 401:
            self.login()
            response = request_with_retry(
                self.http, "GET", url, params=params, headers=self._headers(), sleep=self.sleep
            )
        return response

    def fetch_all(self, path: str, params: dict) -> list[dict]:
        """Every row for one query, across all pages. No data gives an empty list."""
        rows: list[dict] = []
        for page in range(1, self.max_pages + 1):
            response = self._get(path, {**params, "page": page, "Format": "JSON"})
            if response.status_code == 404:
                break  # MoSPI's "No Data Found"
            if response.status_code >= 400:
                raise MospiError(
                    f"{path} {params} page {page}: HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
            body = response.json()
            batch = _find_rows(body)
            if not batch:
                break
            rows.extend(batch)
            total = _total_pages(body)
            if total is None or page >= total:
                break
            self.sleep(self.delay)
        else:
            raise MospiError(f"{path} {params}: more than {self.max_pages} pages")
        return rows


@dataclass(frozen=True)
class Dataset:
    """One MoSPI table: where it lives, which queries cover it and how fields map to columns."""

    name: str
    path: str
    # bronze column -> (API field, DuckDB type)
    fields: dict[str, tuple[str, str]]
    queries: Callable[[date], list[dict]]

    @property
    def columns(self) -> dict[str, str]:
        return {column: kind for column, (_, kind) in self.fields.items()}

    def convert(self, row: dict, source_ref: str) -> dict:
        missing = [api for api, _ in self.fields.values() if api not in row]
        if missing:
            raise MospiError(f"{self.name}: fields {missing} missing; got {sorted(row)}")
        record: dict = {"_source_ref": source_ref}
        for column, (api, kind) in self.fields.items():
            value = row[api]
            if kind == "DOUBLE":
                record[column] = to_float(value)
            elif value is None or str(value).strip() == "":
                record[column] = None
            else:
                record[column] = str(value).strip()
        return record


def _agri_years(first: int, last: int) -> list[str]:
    return [f"{y}-{(y + 1) % 100:02d}" for y in range(first, last + 1)]


def _cpi_queries(today: date) -> list[dict]:
    # General index, Food and beverages, Consumer Food Price index. The 2012-base series
    # ends in December 2025; later years return no data and are skipped.
    return [
        {"base_year": "2012", "series": "Current", "year": str(year), "group_code": group}
        for year in range(2013, today.year + 1)
        for group in ("8", "1", "7")
    ]


def _plfs_queries(today: date) -> list[dict]:
    # LFPR, WPR and unemployment rate. July–June years have no frequency code;
    # calendar years use frequency_code=1 (annual).
    indicators = ("1", "2", "3")
    july_june = [
        {"indicator_code": i, "year": fy} for i in indicators for fy in _agri_years(2017, 2023)
    ]
    calendar_years = [
        {"indicator_code": i, "frequency_code": "1", "year": str(y)}
        for i in indicators
        for y in range(2022, today.year + 1)
    ]
    return july_june + calendar_years


def _asi_queries(today: date) -> list[dict]:
    # Factories, total output, GVA, persons engaged, workers; all industries, NIC 2008.
    return [
        {
            "classification_year": "2008",
            "sector_code": "Combined",
            "nic_type": "All",
            "indicator_code": indicator,
            "year": fy,
        }
        for indicator in ("1", "15", "19", "31", "32")
        for fy in _agri_years(2008, today.year - 1)
    ]


CPI = Dataset(
    name="mospi_cpi",
    path="/api/cpi/getCPIIndex",
    fields={
        "base_year": ("baseyear", "VARCHAR"),
        "year": ("year", "VARCHAR"),
        "month": ("month", "VARCHAR"),
        "state": ("state", "VARCHAR"),
        "sector": ("sector", "VARCHAR"),
        "group_name": ("group", "VARCHAR"),
        "subgroup": ("subgroup", "VARCHAR"),
        "index_value": ("index", "DOUBLE"),
        "inflation": ("inflation", "DOUBLE"),
        "status": ("status", "VARCHAR"),
    },
    queries=_cpi_queries,
)

PLFS = Dataset(
    name="mospi_plfs",
    path="/api/plfs/getData",
    fields={
        "year_type": ("year_type", "VARCHAR"),
        "year": ("year", "VARCHAR"),
        "frequency": ("frequency", "VARCHAR"),
        "indicator": ("indicator", "VARCHAR"),
        "state": ("state", "VARCHAR"),
        "gender": ("gender", "VARCHAR"),
        "sector": ("sector", "VARCHAR"),
        "age_group": ("AgeGroup", "VARCHAR"),
        "weekly_status": ("weekly_status", "VARCHAR"),
        "religion": ("religion", "VARCHAR"),
        "social_group": ("socialGroup", "VARCHAR"),
        "education": ("General_Education", "VARCHAR"),
        "quarter": ("quarter", "VARCHAR"),
        "month": ("month", "VARCHAR"),
        "value": ("value", "DOUBLE"),
        "unit": ("unit", "VARCHAR"),
    },
    queries=_plfs_queries,
)

ASI = Dataset(
    name="mospi_asi",
    path="/api/asi/getASIData",
    fields={
        "nic_classification": ("nic_classification", "VARCHAR"),
        "year": ("year", "VARCHAR"),
        "state": ("state", "VARCHAR"),
        "sector": ("sector", "VARCHAR"),
        "indicator": ("indicator", "VARCHAR"),
        "nic_code": ("nic_code", "VARCHAR"),
        "nic_description": ("nic_description", "VARCHAR"),
        "nic_type": ("nic_type", "VARCHAR"),
        "value": ("value", "DOUBLE"),
        "unit": ("unit", "VARCHAR"),
    },
    queries=_asi_queries,
)

DATASETS = {d.name: d for d in (CPI, PLFS, ASI)}


def collect(client: MospiClient, dataset: Dataset, queries: Iterable[dict]) -> list[dict]:
    records: list[dict] = []
    for params in queries:
        ref = f"{BASE_URL}{dataset.path}?{urlencode(params)}"
        rows = client.fetch_all(dataset.path, params)
        log.info("%s %s: %s rows", dataset.name, params, len(rows))
        records.extend(dataset.convert(row, ref) for row in rows)
        client.sleep(client.delay)
    return records


def run(
    dataset_name: str,
    out_dir: Path,
    *,
    client: MospiClient | None = None,
    today: date | None = None,
) -> Path:
    today = today or date.today()
    dataset = DATASETS[dataset_name]
    if client is None:
        email, password = os.environ.get("MOSPI_EMAIL"), os.environ.get("MOSPI_PASSWORD")
        if not email or not password:
            raise MospiError(
                "MOSPI_EMAIL and MOSPI_PASSWORD must be set (GitHub: Settings > Secrets > Actions)"
            )
        client = MospiClient(email, password)
    records = collect(client, dataset, dataset.queries(today))
    return save_bronze(
        records, dataset.columns, load_source_contract(dataset.name), out_dir, today=today
    )
