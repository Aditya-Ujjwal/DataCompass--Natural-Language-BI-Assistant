from typing import Any

try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)
from pydantic import BaseModel

from config import GEMINI_API_KEY, GEMINI_MODEL
from sql_executor import execute_sql
from sql_validator import validate_sql
from guardrails import check_sql


class SQLCorrection(BaseModel):
    """Structured corrected SQL returned by the LLM."""

    sql: str


def build_correction_prompt(sql: str, error: str, schema: dict, dialect: str = "SQLite") -> str:
    schema_lines = []
    for table_name, columns in schema.items():
        schema_lines.append(f"Table: {table_name}")
        for column in columns:
            schema_lines.append(f"  - {column['name']} ({column['type']})")

    return f"""
You are correcting SQL for a business intelligence application.

DATABASE DIALECT
{dialect}

FAILED SQL
{sql}

DATABASE ERROR
{error}

DATABASE SCHEMA
{chr(10).join(schema_lines)}

RULES
1. Return exactly one corrected SQL query.
2. Use only tables and columns present in the schema.
3. Generate read-only SELECT SQL only.
4. Use syntax compatible with the specified database dialect.
5. Preserve the original analytical intent.
6. Do not explain the correction.
""".strip()


def correct_sql(sql: str, error: str, schema: dict, dialect: str = "SQLite", model: str | None = None) -> SQLCorrection:
    if not GEMINI_API_KEY or genai is None or genai.Client is None:
        raise ValueError(
            "GEMINI_API_KEY / Google GenAI SDK is not configured for SQL recovery."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = build_correction_prompt(sql, error, schema, dialect)

    response = client.models.generate_content(
        model=model or GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": SQLCorrection,
        },
    )

    if not response.text:
        raise RuntimeError("The LLM returned an empty corrected SQL response.")

    return SQLCorrection.model_validate_json(response.text)


def execute_with_recovery(
    engine: Any,
    sql: str,
    schema: dict,
    dialect: str = "SQLite",
    max_retries: int = 2,
) -> dict[str, Any]:
    """Execute SQL, correct execution failures with the LLM, and retry a limited number of times."""
    current_sql = sql
    retries = 0
    errors: list[str] = []

    while True:
        safety = check_sql(current_sql)
        if not safety.allowed:
            return {
                "status": "error", "columns": [], "rows": [], "row_count": 0,
                "execution_time": 0.0, "error": safety.reason, "retries": retries,
                "attempted_sql": current_sql, "recovery_errors": errors,
            }
        validation = validate_sql(current_sql, schema, dialect=dialect)

        if not validation.is_valid:
            return {
                "status": "error",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time": 0.0,
                "error": validation.message,
                "retries": retries,
                "attempted_sql": current_sql,
                "recovery_errors": errors,
            }

        result = execute_sql(engine, current_sql)
        result["retries"] = retries
        result["attempted_sql"] = current_sql
        result["recovery_errors"] = errors

        if result["status"] == "success":
            return result

        errors.append(result["error"])

        if retries >= max_retries:
            return result

        try:
            correction = correct_sql(
                sql=current_sql,
                error=result["error"],
                schema=schema,
                dialect=dialect,
            )
        except Exception as exc:
            errors.append(f"Recovery unavailable: {exc}")
            result["recovery_errors"] = errors
            result["retries"] = retries
            result["attempted_sql"] = current_sql
            return result

        current_sql = correction.sql
        retries += 1
