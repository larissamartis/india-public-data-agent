"""Small code-only steps: worked examples, correlation maths, caveat rules, charts, cache."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from bharat.eval.questions import load_questions

# ---------------------------------------------------------------- worked examples (dev only)

_TASK_OF_TYPE = {
    "single_fact": "single_fact",
    "matching_trap": "single_fact",
    "ranking": "ranking",
    "change_over_time": "change",
    "scaled_comparison": "scaled",
    "combining_sources": "combine",
    "trend": "trend",
    "groups": "group",
}


def worked_examples(task: str, limit: int = 4) -> list[tuple[str, str]]:
    """(question, SQL) pairs from the dev split only; the test split is never shown."""
    pool = [q for q in load_questions("dev") if q.gold_sql and q.type in _TASK_OF_TYPE]
    same = [q for q in pool if _TASK_OF_TYPE[q.type] == task]
    other = [q for q in pool if _TASK_OF_TYPE[q.type] != task and q.type == "single_fact"]
    chosen = (same + other)[:limit]
    return [(" ".join(q.question.split()), q.gold_sql.strip()) for q in chosen]


# ---------------------------------------------------------------- maths


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(sxx * syy)


def correlation(rows: list[tuple]) -> dict | None:
    """Pearson and Spearman r with n, from rows of (label, x, y)."""
    pairs = [
        (float(r[-2]), float(r[-1]))
        for r in rows
        if len(r) >= 3 and isinstance(r[-2], int | float) and isinstance(r[-1], int | float)
    ]
    if len(pairs) < 3:
        return None
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    return {
        "pearson": pearson(xs, ys),
        "spearman": pearson(_ranks(xs), _ranks(ys)),
        "n": len(pairs),
    }


# ---------------------------------------------------------------- caveats

CAVEAT_TEXT = {
    "provisional": (
        "GST figures are provisional and are counted by the state where the taxpayer is "
        "registered, not where goods are consumed."
    ),
    "projection": "Population figures are projections made in 2019 from Census 2011, not counts.",
    "service_area": (
        "Telecom figures are by TRAI licensed service area, not by state; some service areas "
        "cover more than one state."
    ),
    "ladakh_in_jk": "RBI's Jammu and Kashmir figures include Ladakh up to 2018-19.",
    "dnh_merged": (
        "Dadra and Nagar Haveli and Daman and Diu were merged into one UT in January 2020; "
        "figures from then cover both."
    ),
    "state_formed": (
        "Part of the period is before the state was formed; the figure is for its present "
        "area, as published later."
    ),
    "recompute": (
        "A group's ratio is recomputed from totals (or population-weighted), not a simple "
        "average of the state figures."
    ),
    "causation": (
        "This shows how the measures move together across states (correlation); it cannot "
        "show that one causes the other."
    ),
}


def caveat_ids(
    metric_ids: list[str],
    combine_rules: dict[str, str],
    task: str,
    causal: bool,
    sql: str,
    gate_caveats: set[str],
    jk_before_2019: bool,
) -> list[str]:
    found = set(gate_caveats)
    if any(m.startswith("gst_") for m in metric_ids):
        found.add("provisional")
    if any(m.startswith("population") for m in metric_ids):
        found.add("projection")
    if "wireless_subscribers" in metric_ids:
        found.add("service_area")
    if jk_before_2019:
        found.add("ladakh_in_jk")
    ratio = any(combine_rules.get(m) == "recompute" for m in metric_ids) or "/" in sql
    if task == "group" and ratio:
        found.add("recompute")
    if causal or task == "correlation":
        found.add("causation")
    return [c for c in CAVEAT_TEXT if c in found]


# ---------------------------------------------------------------- charts


@dataclass(frozen=True)
class ChartSpec:
    kind: str  # 'bar', 'line' or 'scatter'
    x: str
    y: str
    title: str


def chart_for(task: str, columns: list[str], rows: list[tuple], title: str) -> ChartSpec | None:
    if len(rows) < 2 or len(columns) < 2:
        return None
    if task == "trend":
        return ChartSpec("line", columns[0], columns[1], title)
    if task == "correlation" and len(columns) >= 3:
        return ChartSpec("scatter", columns[-2], columns[-1], title)
    if task in ("ranking", "scaled", "combine", "group"):
        return ChartSpec("bar", columns[0], columns[1], title)
    return None


# ---------------------------------------------------------------- cache


def _key(question: str, data_version: str) -> str:
    normalised = re.sub(r"\s+", " ", question.strip().lower())
    return hashlib.sha256(f"{data_version}\n{normalised}".encode()).hexdigest()


class AnswerCache:
    """Same question on the same data version returns the saved answer."""

    def __init__(self, folder: Path | None):
        self.folder = folder

    def get(self, question: str, data_version: str) -> dict | None:
        if not self.folder:
            return None
        path = self.folder / f"{_key(question, data_version)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def put(self, question: str, data_version: str, result: dict) -> None:
        if not self.folder:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{_key(question, data_version)}.json"
        path.write_text(json.dumps(result, default=str), encoding="utf-8")
