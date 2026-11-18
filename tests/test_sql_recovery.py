import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sql_recovery import SQLCorrection, build_correction_prompt, execute_with_recovery


def make_schema():
    return {
        "sales": [
            {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
            {"name": "city", "type": "TEXT", "nullable": False, "primary_key": False},
            {"name": "revenue", "type": "REAL", "nullable": False, "primary_key": False},
            {"name": "sale_date", "type": "TEXT", "nullable": False, "primary_key": False},
        ]
    }


def test_correction_prompt_contains_error_and_dialect():
    prompt = build_correction_prompt(
        "SELECT missing FROM sales;",
        "no such column: missing",
        make_schema(),
        "SQLite",
    )
    assert "SQLite" in prompt
    assert "no such column: missing" in prompt
    assert "SELECT missing FROM sales;" in prompt
    assert "revenue" in prompt


def test_execute_with_recovery_returns_success_after_correction():
    initial_sql = "SELECT missing_column FROM sales;"
    corrected_sql = "SELECT city, revenue FROM sales;"
    validation_results = iter([
        type("Validation", (), {"is_valid": True, "message": "SQL validation passed."})(),
        type("Validation", (), {"is_valid": True, "message": "SQL validation passed."})(),
    ])
    execution_results = iter([
        {"status": "error", "columns": [], "rows": [], "row_count": 0, "execution_time": 0.001, "error": "no such column: missing_column"},
        {"status": "success", "columns": ["city", "revenue"], "rows": [["Delhi", 190000.0]], "row_count": 1, "execution_time": 0.001, "error": None},
    ])
    with patch("sql_recovery.validate_sql", side_effect=lambda *a, **k: next(validation_results)), \
         patch("sql_recovery.execute_sql", side_effect=lambda *a, **k: next(execution_results)), \
         patch("sql_recovery.correct_sql", return_value=SQLCorrection(sql=corrected_sql)):
        result = execute_with_recovery(object(), initial_sql, make_schema(), max_retries=2)
    assert result["status"] == "success"
    assert result["retries"] == 1
    assert result["attempted_sql"] == corrected_sql


def test_recovery_stops_after_max_retries():
    validation = type("Validation", (), {"is_valid": True, "message": "SQL validation passed."})()
    failed_execution = {"status": "error", "columns": [], "rows": [], "row_count": 0, "execution_time": 0.001, "error": "database syntax error"}
    correction = SQLCorrection(sql="SELECT city FROM sales;")
    with patch("sql_recovery.validate_sql", return_value=validation), \
         patch("sql_recovery.execute_sql", return_value=failed_execution), \
         patch("sql_recovery.correct_sql", return_value=correction) as mock_correct:
        result = execute_with_recovery(object(), "SELECT broken FROM sales;", make_schema(), max_retries=2)
    assert result["status"] == "error"
    assert result["retries"] == 2
    assert len(result["recovery_errors"]) == 3
    assert mock_correct.call_count == 2


def test_invalid_corrected_sql_is_not_executed():
    initial_validation = type("Validation", (), {"is_valid": True, "message": "SQL validation passed."})()
    invalid_corrected_validation = type("Validation", (), {"is_valid": False, "message": "Unknown column: profit."})()
    correction = SQLCorrection(sql="SELECT profit FROM sales;")
    execution_result = {"status": "error", "columns": [], "rows": [], "row_count": 0, "execution_time": 0.001, "error": "no such column"}
    with patch("sql_recovery.validate_sql", side_effect=[initial_validation, invalid_corrected_validation]), \
         patch("sql_recovery.execute_sql", return_value=execution_result) as mock_execute, \
         patch("sql_recovery.correct_sql", return_value=correction):
        result = execute_with_recovery(object(), "SELECT broken FROM sales;", make_schema(), max_retries=2)
    assert result["status"] == "error"
    assert result["error"] == "Unknown column: profit."
    assert mock_execute.call_count == 1
