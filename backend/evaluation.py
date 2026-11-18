from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

from database import get_engine, initialize_database
from intent import understand_question
from query_plan import create_query_plan
from schema import get_database_schema
from sql_generator import generate_sql
from sql_validator import validate_sql
from sql_executor import execute_sql


@dataclass
class EvaluationCase:
    """One benchmark question with an expected analytical result."""

    id: int
    question: str
    expected_city: str | None
    expected_value: float | None


def load_benchmark(path: Path) -> list[EvaluationCase]:
    """Load evaluation cases from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))

    return [
        EvaluationCase(
            id=item["id"],
            question=item["question"],
            expected_city=item.get("expected_city"),
            expected_value=item.get("expected_value"),
        )
        for item in data
    ]


def extract_result_value(result: dict[str, Any]) -> tuple[str | None, float | None]:
    """Extract the first city/value pair when present."""
    rows = result.get("rows", [])

    if not rows:
        return None, None

    row = rows[0]

    if len(row) == 1:
        try:
            return None, float(row[0])
        except (TypeError, ValueError):
            return None, None

    city = row[0]
    try:
        value = float(row[1])
    except (TypeError, ValueError):
        value = None

    return city, value


def evaluate_case(
    case: EvaluationCase,
    engine,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Run one benchmark case through the analytical pipeline."""
    try:
        intent = understand_question(case.question)
        plan = create_query_plan(intent, schema)
        sql_result = generate_sql(plan, schema)

        validation = validate_sql(sql_result.sql, schema)

        if not validation.is_valid:
            return {
                "id": case.id,
                "question": case.question,
                "status": "failed_validation",
                "correct": False,
                "error": validation.message,
            }

        execution = execute_sql(engine, sql_result.sql)

        if execution["status"] != "success":
            return {
                "id": case.id,
                "question": case.question,
                "status": "execution_error",
                "correct": False,
                "error": execution["error"],
            }

        actual_city, actual_value = extract_result_value(execution)

        city_correct = (
            case.expected_city is None
            or actual_city == case.expected_city
        )

        value_correct = (
            case.expected_value is None
            or (
                actual_value is not None
                and abs(actual_value - case.expected_value) < 0.01
            )
        )

        correct = city_correct and value_correct

        return {
            "id": case.id,
            "question": case.question,
            "status": "success",
            "correct": correct,
            "expected_city": case.expected_city,
            "actual_city": actual_city,
            "expected_value": case.expected_value,
            "actual_value": actual_value,
            "sql": sql_result.sql,
        }

    except Exception as exc:
        return {
            "id": case.id,
            "question": case.question,
            "status": "error",
            "correct": False,
            "error": str(exc),
        }


def evaluate_benchmark(path: Path) -> dict[str, Any]:
    """Run all benchmark cases and return a simple evaluation report."""
    initialize_database()

    engine = get_engine()
    schema = get_database_schema(engine)
    cases = load_benchmark(path)

    results = [
        evaluate_case(case, engine, schema)
        for case in cases
    ]

    correct_count = sum(
        1 for result in results if result["correct"]
    )

    total = len(results)
    accuracy = correct_count / total if total else 0.0

    return {
        "total_cases": total,
        "correct_cases": correct_count,
        "accuracy": accuracy,
        "results": results,
    }
