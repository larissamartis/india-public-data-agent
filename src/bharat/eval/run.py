"""Run setups over a split, score every answer, and write the report.

Results go to eval/results/<setup>_<split>.jsonl, one line per question with the output
and its score. A run resumes where it stopped (questions already in the file are skipped),
so a free-tier rate limit or timeout loses nothing. Every test-split run is counted in
eval/results/test_runs.json, because the report must say how often the test set was used.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bharat.agent.llm import LLMBase
from bharat.agent.pipeline import Agent
from bharat.eval.questions import EVAL_DIR, Question, load_questions
from bharat.eval.score import Output, score, wilson
from bharat.eval.setups import plain, run_agent

log = logging.getLogger(__name__)

RESULTS = EVAL_DIR / "results"
SETUPS = ("plain", "no_metrics", "full")
SETUP_NAMES = {
    "plain": "Plain LLM (no data)",
    "no_metrics": "Agent without metrics layer",
    "full": "Full agent",
}


def _gold() -> dict:
    return json.loads((EVAL_DIR / "gold.json").read_text(encoding="utf-8"))


def _latest(path: Path) -> dict[str, dict]:
    """The latest record per question (a retried question appears more than once)."""
    if not path.exists():
        return {}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {record["id"]: record for record in records}


def _pending(record: dict) -> bool:
    """Every LLM call failed (no key, rate limit, wrong model name): the question was never
    really answered, so it is retried on the next run and left out of the scores."""
    return record["output"]["status"] == "error" and record["output"]["stage"] == "llm"


def _done(path: Path) -> set[str]:
    """Questions with a real answer."""
    return {qid for qid, record in _latest(path).items() if not _pending(record)}


def count_test_run(setup: str, results: Path = RESULTS) -> int:
    path = results / "test_runs.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"runs": []}
    data["runs"].append(
        {"setup": setup, "started": datetime.now(UTC).isoformat(timespec="seconds")}
    )
    data["count"] = len(data["runs"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return data["count"]


STOP_AFTER = 5  # questions in a row with no LLM reply before a run stops


def run(
    setup: str,
    split: str,
    llm: LLMBase,
    limit: int = 0,
    results: Path = RESULTS,
    agent_factory=Agent,
) -> Path:
    questions: list[Question] = load_questions(split)
    gold = _gold()["questions"]
    path = results / f"{setup}_{split}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done = _done(path)
    todo = [q for q in questions if q.id not in done]
    if limit:
        todo = todo[:limit]
    if split == "test" and todo:
        log.info("test run number %s", count_test_run(setup, results))
    agent = None
    if setup != "plain":
        agent = agent_factory(llm, metrics_layer=setup == "full")
    failed_in_a_row = 0
    with path.open("a", encoding="utf-8") as handle:
        for q in todo:
            if failed_in_a_row >= STOP_AFTER:
                log.warning(
                    "%s: %s questions in a row got no LLM reply (quota used up?); stopping, "
                    "the next run resumes",
                    setup,
                    STOP_AFTER,
                )
                break
            out: Output = plain(llm, q) if setup == "plain" else run_agent(agent, setup, q)
            result = score(q, out, gold[q.id])
            handle.write(
                json.dumps({"id": q.id, "output": asdict(out), "score": asdict(result)}) + "\n"
            )
            handle.flush()
            failed_in_a_row = failed_in_a_row + 1 if _pending({"output": asdict(out)}) else 0
            log.info(
                "%s %s %s: %s",
                setup,
                q.id,
                out.status,
                "correct" if result.correct else result.failed_step,
            )
    return path


# ---------------------------------------------------------------- report


def _load(results: Path) -> dict[tuple[str, str], list[dict]]:
    found: dict[tuple[str, str], list[dict]] = {}
    for path in sorted(results.glob("*_*.jsonl")):
        setup, split = path.stem.rsplit("_", 1)
        found[(setup, split)] = list(_latest(path).values())
    return found


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def test_run_count(results: Path = RESULTS) -> int:
    path = results / "test_runs.json"
    return json.loads(path.read_text(encoding="utf-8")).get("count", 0) if path.exists() else 0


def summarise(data: dict[tuple[str, str], list[dict]]) -> list[dict]:
    """One row per setup and split, in report order; the report and the app both use it."""
    rows = []
    for (setup, split), records in sorted(
        data.items(), key=lambda kv: (kv[0][1], SETUPS.index(kv[0][0]) if kv[0][0] in SETUPS else 9)
    ):
        answered = [r for r in records if not _pending(r)]
        n = len(answered)
        scores = [r["score"] for r in answered]
        outs = [r["output"] for r in answered] or [{"llm_calls": 0, "seconds": 0, "fallbacks": 0}]
        correct = sum(s["correct"] for s in scores)
        low, high = wilson(correct, n)
        answerable = [s for s in scores if s["expected"] == "answer"]
        rows.append(
            {
                "setup": setup,
                "name": SETUP_NAMES.get(setup, setup),
                "split": split,
                "n": n,
                "pending": len(records) - n,
                "correct": correct,
                "rate": correct / n if n else 0.0,
                "low": low,
                "high": high,
                "wrong_answers": sum(s["wrong_answer"] for s in scores),
                "over_refusals": sum(s["over_refusal"] for s in answerable),
                "answerable": len(answerable),
                "caveats_rate": sum(s["caveats_ok"] for s in scores) / n if n else 0.0,
                "calls": statistics.mean(o["llm_calls"] for o in outs),
                "median_seconds": statistics.median(o["seconds"] for o in outs),
                "fallbacks": sum(o["fallbacks"] for o in outs),
            }
        )
    return rows


def by_question_type(
    data: dict[tuple[str, str], list[dict]],
) -> dict[tuple[str, str], dict[str, list[bool]]]:
    """Correct or not, per question type, for each setup and split (in report order)."""
    found: dict[tuple[str, str], dict[str, list[bool]]] = {}
    for row in summarise(data):
        groups: dict[str, list[bool]] = defaultdict(list)
        for record in data[(row["setup"], row["split"])]:
            if _pending(record):
                continue
            groups[record["score"]["type"]].append(record["score"]["correct"])
        found[(row["setup"], row["split"])] = groups
    return found


def report(results: Path = RESULTS) -> tuple[Path, Path]:
    data = _load(results)
    gold = _gold()
    test_runs = test_run_count(results)
    lines = [
        "# Benchmark results",
        "",
        "Generated by `python -m bharat.eval report`. Do not edit by hand.",
        "",
        f"- Data: serving file `{gold['serving_sha256'][:12]}…`, built {gold['built_at']}",
        f"- Test-split runs so far: {test_runs}",
        "- Correct = right status, right figures within tolerance, and every required caveat.",
        "- Intervals are 95% Wilson score intervals.",
        "- Not yet answered = every model call failed (free quota used up); these questions are"
        " left out of the scores and retried on the next run.",
        "",
        "| setup | split | n | not yet answered | correct (95% CI) | wrong answers |"
        " over-refusals | caveats present | LLM calls / question | median seconds | fallbacks |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in summarise(data):
        lines.append(
            f"| {row['name']} | {row['split']} | {row['n']} | {row['pending']} | "
            f"{_pct(row['rate'])} "
            f"({_pct(row['low'])}–{_pct(row['high'])}) | {row['wrong_answers']} | "
            f"{row['over_refusals']} of {row['answerable']} | {_pct(row['caveats_rate'])} | "
            f"{row['calls']:.1f} | {row['median_seconds']:.1f} | {row['fallbacks']} |"
        )
    by_type = by_question_type(data)

    for split in ("dev", "test"):
        keys = [k for k in by_type if k[1] == split]
        if not keys:
            continue
        types = sorted({t for k in keys for t in by_type[k]})
        lines += ["", f"## By question type ({split})", ""]
        lines.append("| type | " + " | ".join(SETUP_NAMES.get(k[0], k[0]) for k in keys) + " |")
        lines.append("|---|" + "---|" * len(keys))
        for t in types:
            cells = []
            for k in keys:
                values = by_type[k].get(t, [])
                cells.append(f"{sum(values)}/{len(values)}" if values else "")
            lines.append(f"| {t} | " + " | ".join(cells) + " |")

    report_path = results / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = [
        "# Error analysis",
        "",
        "Every incorrect answer, labelled by where it went wrong.",
        "",
    ]
    for (setup, split), rows in sorted(data.items()):
        answered = [r for r in rows if not _pending(r)]
        failed = [r for r in answered if not r["score"]["correct"]]
        counts = Counter(r["score"]["failed_step"] for r in failed)
        errors += [
            f"## {SETUP_NAMES.get(setup, setup)} – {split} "
            f"({len(failed)} of {len(answered)} wrong)",
            "",
        ]
        errors += [f"- {label}: {count}" for label, count in counts.most_common()]
        errors += [
            "",
            "| id | type | expected | got | label | missing caveats |",
            "|---|---|---|---|---|---|",
        ]
        for r in failed:
            s = r["score"]
            errors.append(
                f"| {s['id']} | {s['type']} | {s['expected']} | {s['status']} | "
                f"{s['failed_step']} | {', '.join(s['missing_caveats'])} |"
            )
        errors.append("")
    errors_path = (
        EVAL_DIR / "error_analysis.md" if results == RESULTS else results / "error_analysis.md"
    )
    errors_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
    return report_path, errors_path
