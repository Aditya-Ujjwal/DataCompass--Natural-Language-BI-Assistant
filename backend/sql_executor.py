import time
from datetime import date, datetime, time as time_value
from decimal import Decimal
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from config import MAX_RESULT_ROWS


def _json_safe(value: Any) -> Any:
    """Convert driver-specific scalar values to JSON-friendly Python values."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time_value)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def execute_sql(engine: Engine, sql: str, max_rows: int | None = None) -> dict[str, Any]:
    """Execute a previously validated query and cap fetched results for safety."""
    started = time.perf_counter()
    row_cap = max(1, min(int(max_rows or MAX_RESULT_ROWS), 5000))
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            columns = list(result.keys())
            fetched = result.fetchmany(row_cap + 1)
            truncated = len(fetched) > row_cap
            visible_rows = [[_json_safe(value) for value in row] for row in fetched[:row_cap]]
        return {
            "status": "success",
            "columns": columns,
            "rows": visible_rows,
            "row_count": len(visible_rows),
            "execution_time": time.perf_counter() - started,
            "error": None,
            "truncated": truncated,
        }
    except Exception as exc:
        return {
            "status": "error",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "execution_time": time.perf_counter() - started,
            "error": str(exc),
            "truncated": False,
        }
