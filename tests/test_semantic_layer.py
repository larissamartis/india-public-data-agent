"""The MetricFlow metrics must match the metric list in dim_metric (seed_metrics.csv)."""

import csv
from pathlib import Path

import yaml

DBT = Path(__file__).resolve().parents[1] / "dbt"


def _seed() -> list[dict]:
    with (DBT / "seeds" / "seed_metrics.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _metrics() -> dict[str, dict]:
    data = yaml.safe_load((DBT / "models" / "semantic" / "metrics.yml").read_text("utf-8"))
    return {m["name"]: m for m in data["metrics"]}


def test_every_additive_state_metric_has_a_simple_metric():
    additive = {
        row["metric_id"]
        for row in _seed()
        if row["combine_rule"] == "sum" and row["source_id"] != "trai"  # TRAI is by service area
    }
    simple = {name for name, m in _metrics().items() if m["type"] == "simple"}
    assert simple == additive


def test_ratio_metrics_are_never_summed():
    recompute = {row["metric_id"] for row in _seed() if row["combine_rule"] == "recompute"}
    assert recompute, "seed should list some ratio metrics"
    assert not recompute & set(_metrics())


def test_each_simple_metric_filters_to_itself():
    for name, metric in _metrics().items():
        if metric["type"] == "simple":
            assert metric["filter"].endswith(f"= '{name}'"), name
