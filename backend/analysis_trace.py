from typing import Any
from pydantic import BaseModel


class AnalysisTrace(BaseModel):
    """User-facing audit trail for one analytical request."""

    question: str
    intent: dict[str, Any] | None = None
    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    validation: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    answer: str | None = None
    visualization: dict[str, Any] | None = None


def build_analysis_trace(
    question: str,
    intent: Any = None,
    query_plan: Any = None,
    sql: str | None = None,
    validation: Any = None,
    execution: dict[str, Any] | None = None,
    answer: str | None = None,
    visualization: Any = None,
) -> AnalysisTrace:
    """Build a concise, user-facing trace from pipeline outputs."""

    result_summary = None
    if execution is not None:
        result_summary = {
            "status": execution.get("status"),
            "row_count": execution.get("row_count"),
            "columns": execution.get("columns"),
        }

    return AnalysisTrace(
        question=question,
        intent=intent.model_dump() if hasattr(intent, "model_dump") else intent,
        query_plan=query_plan.model_dump() if hasattr(query_plan, "model_dump") else query_plan,
        sql=sql,
        validation=validation.to_dict() if hasattr(validation, "to_dict") else validation,
        execution=execution,
        result_summary=result_summary,
        answer=answer,
        visualization=visualization.model_dump() if hasattr(visualization, "model_dump") else visualization,
    )


def print_analysis_trace(trace: AnalysisTrace) -> None:
    print("\nAnalysis Trace")
    print("=" * 50)
    print(f"Question: {trace.question}")

    if trace.intent:
        print(f"\nIntent: {trace.intent}")
    if trace.query_plan:
        print(f"\nQuery plan: {trace.query_plan}")
    if trace.sql:
        print(f"\nSQL:\n{trace.sql}")
    if trace.validation:
        print(f"\nValidation: {trace.validation}")
    if trace.execution:
        print(
            "\nExecution:"
            f" status={trace.execution.get('status')},"
            f" rows={trace.execution.get('row_count')},"
            f" time={trace.execution.get('execution_time')}"
        )
    if trace.result_summary:
        print(f"\nResult summary: {trace.result_summary}")
    if trace.answer:
        print(f"\nAnswer: {trace.answer}")
    if trace.visualization:
        print(f"\nVisualization: {trace.visualization}")
