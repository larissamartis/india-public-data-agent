"""Benchmark questions: the schema, loading and the rules every question file must keep.

Questions live in `eval/questions/dev.yaml` (tuning and worked examples) and
`eval/questions/test.yaml` (held out; run only at milestones). Gold answers are not stored
in the questions: they come from each question's reference SQL run against the pinned
serving file, so a rebuild can be re-checked rather than silently going stale.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"

QuestionType = Literal[
    "single_fact",
    "ranking",
    "change_over_time",
    "scaled_comparison",
    "combining_sources",
    "trend",
    "groups",
    "matching_trap",
    "cannot_answer",
    "causal_trap",
    "unclear",
]

# Agreed design: 155 questions; 55 in the test split, stratified by type.
PLANNED = {
    "single_fact": (13, 7),
    "ranking": (10, 5),
    "change_over_time": (13, 7),
    "scaled_comparison": (10, 5),
    "combining_sources": (10, 5),
    "trend": (6, 4),
    "groups": (6, 4),
    "matching_trap": (10, 5),
    "cannot_answer": (13, 7),
    "causal_trap": (6, 4),
    "unclear": (3, 2),
}

# Tables reference SQL may read: the marts the agent will see.
ALLOWED_TABLES = frozenset(
    {
        "fct_state_metric",
        "fct_national_metric",
        "fct_lsa_metric",
        "dim_state",
        "dim_metric",
        "dim_source",
        "dim_period",
        "coverage",
    }
)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^(D|T)\d{3}$")
    type: QuestionType
    question: str
    expected: Literal["answer", "refuse", "clarify"]
    kind: Literal["number", "ranking", "series", "correlation", "none"] = "none"
    unit: str | None = None
    gold_sql: str | None = None
    tolerance: float = 0.005  # relative, for numbers and series points
    caveats: list[str] = Field(default_factory=list)
    reason: str | None = None  # why, for refusals
    notes: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Question:
        if self.expected == "answer":
            if self.kind == "none" or not self.gold_sql:
                raise ValueError(f"{self.id}: an answer needs a kind and gold_sql")
        else:
            if self.kind != "none" or self.gold_sql:
                raise ValueError(f"{self.id}: {self.expected} questions have no gold answer")
        if self.expected == "refuse" and not self.reason:
            raise ValueError(f"{self.id}: a refusal needs a reason")
        return self


def load_questions(split: Literal["dev", "test"], folder: Path | None = None) -> list[Question]:
    path = (folder or EVAL_DIR / "questions") / f"{split}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Question.model_validate(item) for item in data["questions"]]


def load_caveats(folder: Path | None = None) -> dict:
    return yaml.safe_load(((folder or EVAL_DIR) / "caveats.yaml").read_text(encoding="utf-8"))


def check_plan(dev: list[Question], test: list[Question]) -> list[str]:
    """Problems with counts, id prefixes, duplicates and caveat or reason names."""
    problems = []
    for split, questions, index, prefix in (("dev", dev, 0, "D"), ("test", test, 1, "T")):
        counts = Counter(q.type for q in questions)
        for kind, planned in PLANNED.items():
            if counts[kind] != planned[index]:
                problems.append(f"{split}: {kind} has {counts[kind]}, planned {planned[index]}")
        problems += [
            f"{split}: {q.id} has the wrong prefix" for q in questions if q.id[0] != prefix
        ]
    ids = Counter(q.id for q in dev + test)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    texts = Counter(q.question.strip().lower() for q in dev + test)
    problems += [f"duplicate question: {t}" for t, n in texts.items() if n > 1]
    catalogue = load_caveats()
    for q in dev + test:
        problems += [
            f"{q.id}: unknown caveat {c}" for c in q.caveats if c not in catalogue["caveats"]
        ]
        if q.reason and q.reason not in catalogue["refusal_reasons"]:
            problems.append(f"{q.id}: unknown reason {q.reason}")
    return problems
