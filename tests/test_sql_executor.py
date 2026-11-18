import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import get_engine, initialize_database
from sql_executor import execute_sql


def test_execute_select_successfully():
    initialize_database()
    result = execute_sql(get_engine(), "SELECT city, revenue FROM sales ORDER BY id;")
    assert result["status"] == "success"
    assert result["columns"] == ["city", "revenue"]
    assert result["row_count"] == 5
    assert result["error"] is None


def test_execute_aggregation_successfully():
    initialize_database()
    result = execute_sql(
        get_engine(),
        """SELECT city, SUM(revenue) AS total_revenue
           FROM sales GROUP BY city ORDER BY total_revenue DESC;""",
    )
    assert result["status"] == "success"
    assert result["row_count"] == 3
    assert result["rows"][0][0] == "Delhi"


def test_execution_error_is_returned():
    initialize_database()
    result = execute_sql(get_engine(), "SELECT missing_column FROM sales;")
    assert result["status"] == "error"
    assert result["row_count"] == 0
    assert result["error"]


def test_execution_result_contains_timing():
    initialize_database()
    result = execute_sql(get_engine(), "SELECT 1;")
    assert result["execution_time"] >= 0


def test_execution_caps_returned_rows():
    initialize_database()
    engine = get_engine()
    result = execute_sql(engine, "SELECT id FROM sales ORDER BY id;", max_rows=2)
    assert result["status"] == "success"
    assert result["row_count"] == 2
    assert result["truncated"] is True


def test_json_safe_converts_decimal_and_date_values():
    from datetime import date
    from decimal import Decimal
    from sql_executor import _json_safe

    assert _json_safe(Decimal("12.5")) == 12.5
    assert _json_safe(Decimal("12")) == 12
    assert _json_safe(date(2026, 11, 4)) == "2026-11-04"
