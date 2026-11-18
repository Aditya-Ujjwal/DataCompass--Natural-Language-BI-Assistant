import time
from typing import Any
from sqlalchemy import text

from analysis_trace import build_analysis_trace
from answer_evaluation import evaluate_answer
from business_context import load_business_context
from config import GEMINI_MODEL, LLM_PROVIDER, OPENAI_MODEL, MAX_RECOVERY_RETRIES
from database import get_engine, using_demo_database
from db_dialect import get_database_dialect
from guardrails import check_answer, check_input, check_sql
from intent import understand_question
from observability import finish_request, record_execution_time, start_request
from query_plan import create_query_plan
from result_analyzer import generate_answer
from schema import get_database_schema, get_database_profile, get_database_relationships
from sql_generator import generate_sql
from sql_recovery import execute_with_recovery
from sql_validator import validate_sql
from visualization import suggest_visualization, VisualizationSpec
from solarpulse_analytics import build_solarpulse_query, build_solarpulse_answer
from sql_generator import SQLResult


def _known_values(engine, schema: dict[str, Any]) -> dict[str, list[str]]:
    """Read a small, bounded sample of categorical values from every table.

    Qualified keys prevent collisions across tables. A bare column name is
    added only when it is unique in the entire database for backwards
    compatibility with simple one-table projects.
    """
    result: dict[str, list[str]] = {}
    preparer = engine.dialect.identifier_preparer
    name_counts: dict[str, int] = {}
    for columns in schema.values():
        for column in columns:
            name = str(column.get("name", ""))
            ctype = str(column.get("type", "")).upper()
            if any(token in ctype for token in ("TEXT", "CHAR", "STRING", "VARCHAR", "ENUM", "CLOB")):
                name_counts[name] = name_counts.get(name, 0) + 1

    with engine.connect() as connection:
        for table, columns in schema.items():
            for col in columns:
                name = col.get("name", "")
                ctype = str(col.get("type", "")).upper()
                if col.get("primary_key") or name.lower().endswith(("_id", "_key", "id", "key")):
                    continue
                if not any(token in ctype for token in ("TEXT", "CHAR", "STRING", "VARCHAR", "ENUM", "CLOB")):
                    continue
                try:
                    quoted_name = preparer.quote(name)
                    quoted_table = preparer.quote(table)
                    rows = connection.execute(
                        text(f"SELECT {quoted_name} FROM {quoted_table} WHERE {quoted_name} IS NOT NULL LIMIT 100")
                    ).fetchall()
                    values = list(dict.fromkeys(str(row[0]) for row in rows if row[0] is not None))[:40]
                    if values:
                        result[f"{table}.{name}"] = values
                        if name_counts.get(name) == 1:
                            result[name] = values
                except Exception:
                    continue
    return result


def _public_database_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Small safe catalog summary attached to each successful response."""
    return {
        "database_type": profile.get("database_type"),
        "dialect": profile.get("dialect"),
        "table_count": profile.get("table_count", 0),
        "tables": [
            {"name": table.get("name"), "kind": table.get("kind"), "column_count": table.get("column_count")}
            for table in profile.get("tables", [])
        ],
        "relationships": profile.get("relationships", []),
    }


def _friendly_error(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()
    if "429" in lower or "resource_exhausted" in lower or "quota" in lower:
        return "The AI model quota is currently exhausted. Wait for the quota reset or disable LLM fallback in backend/.env; supported common queries can still run locally."
    if "503" in lower or "unavailable" in lower or "high demand" in lower:
        return "The AI model is temporarily unavailable. Please retry shortly; common supported BI questions use the local rule-based path."
    if "api key" in lower and "not set" in lower:
        return "No LLM API key is configured. Common supported BI questions are available locally; configure GEMINI_API_KEY for unsupported questions."
    return message


def run_assistant(question: str) -> dict[str, Any]:
    provider = LLM_PROVIDER
    model = GEMINI_MODEL if provider == "gemini" else OPENAI_MODEL if provider == "openai" else None
    metrics = start_request(model=model, provider=provider)
    started = time.perf_counter()
    guard = check_input(question)
    if not guard.allowed:
        finish_request(metrics, time.perf_counter() - started, status="blocked", error=guard.reason)
        return {"status": "blocked", "stage": "input_guardrail", "message": guard.reason, "metrics": metrics.to_dict()}
    try:
        engine = get_engine()
        profile = get_database_profile(engine)
        schema = profile["schema"]
        relationships = profile["relationships"]
        values = _known_values(engine, schema)
        if using_demo_database():
            context = load_business_context()
        else:
            # Do not accidentally apply the sample-sales definitions to a user's database.
            context = {
                "database_description": "User-connected database. Use only discovered schema information.",
                "tables": {table: "Discovered database table." for table in schema},
                "columns": {
                    f"{table}.{column['name']}": f"Database column of type {column.get('type', 'unknown')}."
                    for table, columns in schema.items() for column in columns
                },
                "metrics": {}, "business_rules": [], "terminology": {},
            }
        dialect = get_database_dialect(engine)

        # Apply validated SolarPulse business templates before the generic parser.
        # This prevents ambiguous words such as "worst", "persistent" or "records"
        # from being mapped to an unrelated measure/table by the general rules.
        solar_query = build_solarpulse_query(question, schema, dialect, relationships=relationships)
        if solar_query is not None:
            intent = solar_query.intent
            plan = solar_query.plan
            sql_result = SQLResult(sql=solar_query.sql)
        else:
            intent = understand_question(question, schema=schema, known_values=values)
        if intent.intent == "metadata":
            rows = [
                [table["name"], table["kind"], table["column_count"]]
                for table in profile["tables"]
            ]
            execution = {
                "status": "success",
                "columns": ["table", "type", "column_count"],
                "rows": rows,
                "row_count": len(rows),
                "execution_time": 0.0,
                "error": None,
                "retries": 0,
                "attempted_sql": None,
                "recovery_errors": [],
                "truncated": False,
            }
            answer = (
                f"I discovered {len(rows)} tables/views in the connected database. "
                "Open Database explorer to inspect every column, data type, primary key, and relationship."
            )
            visualization = suggest_visualization(execution, preferred_chart="table")
            finish_request(metrics, time.perf_counter() - started, status="success", result_rows=len(rows), evaluation_score=1.0)
            trace = build_analysis_trace(
                question=question,
                intent=intent,
                query_plan=None,
                sql=None,
                validation={"is_valid": True, "message": "Catalog inspection; no SQL execution required."},
                execution=execution,
                answer=answer,
                visualization=visualization,
            )
            return {
                "status": "success", "question": question,
                "intent": intent.model_dump(), "query_plan": None, "sql": None,
                "execution": execution, "answer": answer,
                "answer_evaluation": {"grounded": True, "reason": "Answer is based on database metadata."},
                "visualization": visualization.model_dump(),
                "analysis_trace": trace.model_dump(), "metrics": metrics.to_dict(),
                "database_profile": _public_database_profile(profile),
            }
        if solar_query is None:
            plan = create_query_plan(intent, schema, relationships=relationships, question=question)
            sql_result = generate_sql(plan, schema, business_context=context, dialect=dialect)
        sql_guard = check_sql(sql_result.sql)
        if not sql_guard.allowed:
            finish_request(metrics, time.perf_counter() - started, status="blocked", error=sql_guard.reason)
            return {"status": "blocked", "stage": "sql_guardrail", "message": sql_guard.reason, "sql": sql_result.sql, "metrics": metrics.to_dict()}

        validation = validate_sql(sql_result.sql, schema, dialect=dialect)
        if not validation.is_valid:
            finish_request(metrics, time.perf_counter() - started, status="error", error=validation.message)
            return {"status": "error", "stage": "sql_validation", "message": validation.message, "sql": sql_result.sql, "metrics": metrics.to_dict()}

        execution = execute_with_recovery(
            engine=engine,
            sql=validation.normalized_sql or sql_result.sql,
            schema=schema,
            dialect=dialect,
            max_retries=MAX_RECOVERY_RETRIES,
        )
        record_execution_time(metrics, execution.get("execution_time"))
        metrics.retries = execution.get("retries", 0)
        if execution.get("status") != "success":
            finish_request(metrics, time.perf_counter() - started, status="error", result_rows=execution.get("row_count", 0), retries=execution.get("retries", 0), error=execution.get("error"))
            return {"status": "error", "stage": "sql_execution", "message": _friendly_error(Exception(execution.get("error") or "SQL execution failed")), "sql": execution.get("attempted_sql", sql_result.sql), "execution": execution, "metrics": metrics.to_dict()}

        if solar_query is not None:
            from result_analyzer import AnalysisResult
            answer_result = AnalysisResult(answer=build_solarpulse_answer(solar_query.answer_kind, execution))
            visualization = solar_query.visualization
        else:
            answer_result = generate_answer(question, execution, query_plan=plan)
            preferred_chart = "table" if intent.intent == "lookup" else intent.chart_type
            visualization = suggest_visualization(execution, preferred_chart=preferred_chart)
        output_guard = check_answer(answer_result.answer, execution)
        if not output_guard.allowed:
            finish_request(metrics, time.perf_counter() - started, status="blocked", result_rows=execution.get("row_count", 0), retries=execution.get("retries", 0), error=output_guard.reason)
            return {"status": "blocked", "stage": "output_guardrail", "message": output_guard.reason, "metrics": metrics.to_dict()}
        answer_eval = evaluate_answer(question, answer_result.answer, execution)
        finish_request(metrics, time.perf_counter() - started, status="success", result_rows=execution.get("row_count", 0), retries=execution.get("retries", 0), evaluation_score=1.0 if answer_eval.grounded else 0.0)
        trace = build_analysis_trace(question=question, intent=intent, query_plan=plan, sql=execution.get("attempted_sql", sql_result.sql), validation={"is_valid": True, "message": validation.message}, execution=execution, answer=answer_result.answer, visualization=visualization)
        return {
            "status": "success", "question": question, "intent": intent.model_dump(),
            "query_plan": plan.model_dump(), "sql": execution.get("attempted_sql", sql_result.sql),
            "execution": execution, "answer": answer_result.answer,
            "answer_evaluation": answer_eval.model_dump(), "visualization": visualization.model_dump(),
            "analysis_trace": trace.model_dump(), "metrics": metrics.to_dict(),
            "database_profile": _public_database_profile(profile),
        }
    except Exception as exc:
        message = _friendly_error(exc)
        finish_request(metrics, time.perf_counter() - started, status="error", error=message)
        return {"status": "error", "stage": "assistant", "message": message, "metrics": metrics.to_dict()}
