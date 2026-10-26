"""Pieces every source shares: a polite HTTP client, number cleaning and file hashing."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "india-public-data-agent/0.1 (+https://github.com/larissamartis/india-public-data-agent)"
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def make_client(
    transport: httpx.BaseTransport | None = None, timeout: float = 60.0
) -> httpx.Client:
    """An HTTP client that says who we are and follows redirects."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
        transport=transport,
    )


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 4,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> httpx.Response:
    """Send a request, waiting longer after each busy or failed reply.

    Returns the last response even if it is an error, so callers decide what an error means
    (MoSPI, for example, answers 401 when a token expires and 404 when there is no data).
    """
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as error:
            if attempt == attempts:
                raise
            log.warning("%s %s failed (%s); retrying", method, url, error)
        else:
            if response.status_code not in RETRY_STATUSES or attempt == attempts:
                return response
            log.warning("%s %s returned %s; retrying", method, url, response.status_code)
        sleep(backoff**attempt)
    raise AssertionError("unreachable")


def to_float(value: object) -> float | None:
    """Read a number from a cell or API field: '1,234.5', 12, '-', '' and None all handled."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if text in {"", "-", "–", "NA", "N.A.", "na", "null", "None", "*"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
