"""Check that every number in an LLM-written answer comes from the query result.

The answer step may only restate figures the SQL returned. This module pulls each number
out of the answer text (including Indian forms such as "1,23,456" and "₹4.2 lakh crore")
and looks for a result value it could be a rounding of. Any number with no source is
reported, so the pipeline can retry or fall back to a template answer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_SCALES = {
    "lakh crore": 1e12,
    "lakh crores": 1e12,
    "thousand crore": 1e10,
    "crore": 1e7,
    "crores": 1e7,
    "lakh": 1e5,
    "lakhs": 1e5,
    "thousand": 1e3,
    "million": 1e6,
    "billion": 1e9,
}
# Units a stored value may already be in; "₹4.2 lakh crore" should match 420000 (₹ crore).
_BASE_UNITS = (1.0, 1e5, 1e7)

_NUMBER = re.compile(
    r"(?<![\w.])(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>"
    + "|".join(sorted((re.escape(s) for s in _SCALES), key=len, reverse=True))
    + r")?(?![\w])",
    re.IGNORECASE,
)
_FY_LABEL = re.compile(r"\b(?:19|20)\d{2}\s*[-–/]\s*\d{2,4}\b")
_DATE_LIKE = re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+(?:19|20)\d{2}\b")


@dataclass(frozen=True)
class Mention:
    text: str
    value: float
    decimals: int
    scale: float


def extract_numbers(text: str) -> list[Mention]:
    """Find numbers in prose, skipping FY labels such as 2023-24 and calendar years."""
    cleaned = _DATE_LIKE.sub(" ", _FY_LABEL.sub(" ", text))
    mentions = []
    for match in _NUMBER.finditer(cleaned):
        raw = match.group("num").replace(",", "")
        scale_word = (match.group("scale") or "").lower()
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw)
        if not scale_word and decimals == 0 and 1900 <= value <= 2100:
            continue  # a year, not a figure
        mentions.append(
            Mention(match.group(0).strip(), value, decimals, _SCALES.get(scale_word, 1.0))
        )
    return mentions


def _matches(mention: Mention, value: float, rel_tol: float) -> bool:
    target = abs(value)
    for base in _BASE_UNITS:
        candidate = mention.value * mention.scale / base
        rounding = 0.5 * 10 ** (-mention.decimals) * mention.scale / base
        if abs(candidate - target) <= rounding * 1.0001:
            return True
        if target and abs(candidate - target) / target <= rel_tol:
            return True
    return False


def unsupported_numbers(
    answer: str,
    result_values: Iterable[float],
    allowed: Iterable[float] = (),
    rel_tol: float = 0.005,
) -> list[str]:
    """Return the numbers in the answer that no result value (or allowed extra) supports.

    `allowed` holds numbers that are legitimate without being in the result, such as
    the "5" in "top 5 states" or the count of states compared.
    """
    pool = [float(v) for v in result_values if v is not None]
    pool += [float(v) for v in allowed]
    return [
        m.text for m in extract_numbers(answer) if not any(_matches(m, v, rel_tol) for v in pool)
    ]
