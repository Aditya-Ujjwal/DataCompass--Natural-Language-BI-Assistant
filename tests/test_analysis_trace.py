import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from analysis_trace import AnalysisTrace, build_analysis_trace


def test_analysis_trace_model():
    trace = AnalysisTrace(
        question="Which city generated the highest revenue?",
        sql="SELECT city, SUM(revenue) FROM sales GROUP BY city;",
        answer="Delhi generated the highest revenue.",
    )

    assert trace.question.startswith("Which city")
    assert "SELECT" in trace.sql
    assert trace.answer.startswith("Delhi")


def test_analysis_trace_builds_result_summary():
    execution = {
        "status": "success",
        "columns": ["city", "total_revenue"],
        "rows": [["Delhi", 190000.0]],
        "row_count": 1,
        "execution_time": 0.001,
        "error": None,
    }

    trace = build_analysis_trace(
        question="Which city generated the highest revenue?",
        execution=execution,
    )

    assert trace.result_summary == {
        "status": "success",
        "row_count": 1,
        "columns": ["city", "total_revenue"],
    }


def test_analysis_trace_handles_model_objects():
    class FakeModel:
        def model_dump(self):
            return {"intent": "ranking"}

    trace = build_analysis_trace(
        question="Which city generated the highest revenue?",
        intent=FakeModel(),
    )

    assert trace.intent == {"intent": "ranking"}


def test_analysis_trace_keeps_execution_details():
    execution = {
        "status": "success",
        "columns": ["city"],
        "rows": [["Delhi"]],
        "row_count": 1,
        "execution_time": 0.002,
        "error": None,
    }

    trace = build_analysis_trace(
        question="Which city generated the highest revenue?",
        execution=execution,
    )

    assert trace.execution["status"] == "success"
    assert trace.execution["row_count"] == 1
    assert trace.execution["execution_time"] == 0.002
