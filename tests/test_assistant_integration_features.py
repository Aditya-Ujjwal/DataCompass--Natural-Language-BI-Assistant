import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "backend"),
)

from assistant import run_assistant
from intent import QueryIntent
from query_plan import QueryPlan
from sql_generator import SQLResult
from result_analyzer import AnalysisResult


def make_intent():
    return QueryIntent(
        intent="ranking",
        metric="revenue",
        dimension="city",
        filters=[],
        time_period=None,
        sort_order="descending",
        limit=1,
    )


def make_plan():
    return QueryPlan(
        goal="Find the city with the highest revenue.",
        table="sales",
        metric_column="revenue",
        dimension_column="city",
        aggregation="SUM",
        filters=[],
        time_period=None,
        sort_order="descending",
        limit=1,
    )


def make_execution():
    return {
        "status": "success",
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0]],
        "row_count": 1,
        "execution_time": 0.001,
        "error": None,
        "retries": 0,
        "attempted_sql": "SELECT city, SUM(revenue) FROM sales GROUP BY city;",
        "recovery_errors": [],
    }


def test_assistant_passes_context_and_dialect_to_sql_generator():
    intent = make_intent()
    plan = make_plan()
    execution = make_execution()

    with patch("assistant.understand_question", return_value=intent),          patch("assistant.create_query_plan", return_value=plan),          patch("assistant.generate_sql", return_value=SQLResult(
             sql="SELECT city, SUM(revenue) FROM sales GROUP BY city;"
         )) as generate_sql,          patch("assistant.execute_with_recovery", return_value=execution),          patch("assistant.generate_answer", return_value=AnalysisResult(
             answer="Delhi generated the highest revenue with 190000."
         )):

        result = run_assistant("Which city generated the highest revenue?")

    assert result["status"] == "success"
    args, kwargs = generate_sql.call_args

    assert kwargs["business_context"]["metrics"]["revenue"]
    assert kwargs["dialect"] == "SQLite"


def test_assistant_records_recovery_retries():
    intent = make_intent()
    plan = make_plan()

    execution = make_execution()
    execution["retries"] = 1

    with patch("assistant.understand_question", return_value=intent),          patch("assistant.create_query_plan", return_value=plan),          patch("assistant.generate_sql", return_value=SQLResult(
             sql="SELECT city FROM sales;"
         )),          patch("assistant.execute_with_recovery", return_value=execution),          patch("assistant.generate_answer", return_value=AnalysisResult(
             answer="Delhi generated the highest revenue with 190000."
         )):

        result = run_assistant("Which city generated the highest revenue?")

    assert result["status"] == "success"
    assert result["execution"]["retries"] == 1
    assert result["metrics"]["retries"] == 1


def test_assistant_returns_grounded_answer_evaluation():
    intent = make_intent()
    plan = make_plan()
    execution = make_execution()

    with patch("assistant.understand_question", return_value=intent),          patch("assistant.create_query_plan", return_value=plan),          patch("assistant.generate_sql", return_value=SQLResult(
             sql="SELECT city, SUM(revenue) FROM sales GROUP BY city;"
         )),          patch("assistant.execute_with_recovery", return_value=execution),          patch("assistant.generate_answer", return_value=AnalysisResult(
             answer="Delhi generated the highest revenue with 190000."
         )),          patch(
             "assistant.evaluate_answer",
             return_value=type(
                 "Eval",
                 (),
                 {
                     "grounded": True,
                     "model_dump": lambda self: {
                         "grounded": True,
                         "reason": "Supported by the database result.",
                     },
                 },
             )(),
         ):

        result = run_assistant("Which city generated the highest revenue?")

    assert result["answer_evaluation"]["grounded"] is True
    assert result["metrics"]["evaluation_score"] == 1.0
