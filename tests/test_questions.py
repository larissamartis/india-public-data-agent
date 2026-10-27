"""The benchmark questions keep the agreed plan, and every gold query works on the pinned data."""

import duckdb
import pytest

from bharat.eval.gold import SERVING_DB, indian, run_gold
from bharat.eval.questions import check_plan, load_questions

DEV = load_questions("dev")
TEST = load_questions("test")
WITH_GOLD = [q for q in DEV + TEST if q.gold_sql]


def test_questions_follow_the_agreed_plan():
    assert check_plan(DEV, TEST) == []
    assert len(DEV) == 100 and len(TEST) == 55


@pytest.fixture(scope="module")
def serving():
    if not SERVING_DB.exists():
        pytest.skip("no serving file; run the Build workflow")
    con = duckdb.connect(str(SERVING_DB), read_only=True)
    yield con
    con.close()


@pytest.mark.parametrize("question", WITH_GOLD, ids=[q.id for q in WITH_GOLD])
def test_gold_sql_runs_and_has_the_right_shape(serving, question):
    run_gold(serving, question)  # raises GoldError with the rows if anything is off


@pytest.mark.parametrize(
    ("value", "text"),
    [(12345678.9, "1,23,45,678.90"), (999.5, "999.50"), (-150000, "-1,50,000.00"), (0, "0.00")],
)
def test_indian_number_format(value, text):
    assert indian(value) == text
