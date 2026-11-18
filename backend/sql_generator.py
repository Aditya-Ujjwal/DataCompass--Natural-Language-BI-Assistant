from datetime import date, timedelta
import re
from pydantic import BaseModel

try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)

from config import GEMINI_API_KEY, GEMINI_MODEL, ENABLE_LLM_FALLBACK, MAX_RESULT_ROWS


class SQLResult(BaseModel):
    sql: str


def _quote_ident(value: str, dialect: str = "SQLite") -> str:
    """Quote an identifier discovered from the live database schema.

    Identifiers are never accepted from raw user text: callers pass names that
    already exist in the inspected schema. Quoting therefore safely supports
    spaces, reserved words, punctuation, and embedded quote characters.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Invalid SQL identifier.")
    quote = "`" if dialect.lower() in {"mysql", "mariadb"} else '"'
    escaped = value.replace(quote, quote + quote)
    return f"{quote}{escaped}{quote}"


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _time_bounds(period: str | None, today: date | None = None) -> tuple[str, str] | None:
    if not period:
        return None
    today = today or date.today()
    phrase = period.lower().strip()
    current_month = _month_start(today)
    current_quarter = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
    current_year = date(today.year, 1, 1)
    if phrase in {"last quarter", "previous quarter"}:
        return _add_months(current_quarter, -3).isoformat(), current_quarter.isoformat()
    if phrase == "this quarter":
        return current_quarter.isoformat(), _add_months(current_quarter, 3).isoformat()
    if phrase in {"last month", "previous month"}:
        return _add_months(current_month, -1).isoformat(), current_month.isoformat()
    if phrase == "this month":
        return current_month.isoformat(), _add_months(current_month, 1).isoformat()
    if phrase in {"last year", "previous year"}:
        return date(today.year - 1, 1, 1).isoformat(), current_year.isoformat()
    if phrase == "this year":
        return current_year.isoformat(), date(today.year + 1, 1, 1).isoformat()
    if phrase == "last 30 days":
        return (today - timedelta(days=29)).isoformat(), (today + timedelta(days=1)).isoformat()
    if phrase == "last 7 days":
        return (today - timedelta(days=6)).isoformat(), (today + timedelta(days=1)).isoformat()
    raise NotImplementedError(f"Time period '{period}' isn't supported yet.")


def build_sql_prompt(query_plan, schema: dict, business_context: dict | None = None, dialect: str = "SQLite") -> str:
    schema_text = []
    for table_name, columns in schema.items():
        schema_text.append(f"Table: {table_name}")
        schema_text.extend(f"  - {c['name']} ({c.get('type', 'unknown')})" for c in columns)
    context_text = ""
    if business_context:
        from business_context import context_to_prompt_text
        context_text = "\nBUSINESS / DATABASE CONTEXT\n" + context_to_prompt_text(business_context)
    return f"""
You generate exactly one safe, read-only SELECT statement for a BI assistant.
Database dialect: {dialect}.
Use only the full discovered schema below and follow the business rules.
The query plan may include explicit foreign-key join steps. Use those joins exactly;
do not guess relationships or join unrelated tables.
Query plan: {query_plan.model_dump() if hasattr(query_plan, 'model_dump') else query_plan.__dict__}
Schema:\n{chr(10).join(schema_text)}
{context_text}
Return structured SQL only. Do not invent columns, tables, or metrics.
""".strip()


def build_sql_deterministically(query_plan, schema: dict, dialect: str = "SQLite") -> str:
    """Build controlled SELECT SQL, including discovered FK joins when required."""
    if dialect.lower() not in {"sqlite", "postgresql", "postgres", "mysql", "mariadb"}:
        raise NotImplementedError(f"Deterministic SQL generation does not support {dialect} yet.")

    table_columns = {
        table_name: {str(column["name"]) for column in columns}
        for table_name, columns in schema.items()
    }
    base_table = query_plan.table
    if base_table not in table_columns:
        raise ValueError(f"Unknown table in query plan: {base_table}")

    q = lambda name: _quote_ident(name, dialect)
    included_tables = [base_table]
    joins_sql: list[str] = []
    aliases = {base_table: "t0"}

    for edge in getattr(query_plan, "joins", []) or []:
        from_table = edge["from_table"]
        to_table = edge["to_table"]
        from_column = edge["from_column"]
        to_column = edge["to_column"]
        if from_table not in table_columns or to_table not in table_columns:
            raise ValueError("A planned join references a table outside the discovered schema.")
        if from_column not in table_columns[from_table] or to_column not in table_columns[to_table]:
            raise ValueError("A planned join references a column outside the discovered schema.")
        if from_table not in aliases:
            raise ValueError(f"Join path is incomplete: '{from_table}' has not been joined yet.")
        if to_table in aliases:
            continue
        alias = f"t{len(aliases)}"
        aliases[to_table] = alias
        included_tables.append(to_table)
        joins_sql.append(
            f"JOIN {q(to_table)} AS {q(alias)} ON "
            f"{q(aliases[from_table])}.{q(from_column)} = {q(alias)}.{q(to_column)}"
        )

    def column_expr(table: str | None, column: str) -> str:
        actual_table = table or base_table
        if actual_table not in aliases:
            raise ValueError(f"Column table '{actual_table}' is not part of the query join path.")
        if column not in table_columns.get(actual_table, set()):
            raise ValueError(f"Unknown column: {actual_table}.{column}")
        # Keep one-table SQL readable; qualify identifiers when joins could make
        # column references ambiguous.
        if len(aliases) == 1:
            return q(column)
        return f"{q(aliases[actual_table])}.{q(column)}"

    where_parts: list[str] = []
    for item in query_plan.filters or []:
        if "=" not in item:
            raise ValueError(f"Unsupported filter format: {item}")
        raw_column, raw_value = item.split("=", 1)
        raw_column = raw_column.strip()
        raw_value = raw_value.strip()
        if "." in raw_column:
            filter_table, filter_column = raw_column.rsplit(".", 1)
        else:
            filter_column = raw_column
            possible_tables = [table for table in included_tables if filter_column in table_columns[table]]
            if len(possible_tables) == 1:
                filter_table = possible_tables[0]
            elif filter_column in table_columns[base_table]:
                filter_table = base_table
            else:
                raise ValueError(f"Filter references ambiguous or unknown column: {filter_column}")
        where_parts.append(f"{column_expr(filter_table, filter_column)} = {_quote_literal(raw_value)}")

    metric = query_plan.metric_column
    dimension = query_plan.dimension_column
    metric_table = getattr(query_plan, "metric_table", None) or base_table
    dimension_table = getattr(query_plan, "dimension_table", None) or base_table
    time_table = getattr(query_plan, "time_table", None) or base_table
    time_column = getattr(query_plan, "time_column", None)
    chart_type = getattr(query_plan, "chart_type", None)

    if query_plan.time_period:
        if not time_column:
            # Find a date/time field among the joined tables, preferring base table.
            for candidate_table in included_tables:
                candidate = next((column["name"] for column in schema[candidate_table]
                                  if "date" in str(column.get("type", "")).lower()
                                  or "time" in str(column.get("type", "")).lower()
                                  or re.search(r"(^|_)(date|time|timestamp|datetime)(_|$)", str(column["name"]).lower())), None)
                if candidate:
                    time_table, time_column = candidate_table, candidate
                    break
        bounds = _time_bounds(query_plan.time_period)
        if not time_column or time_table not in aliases:
            raise ValueError("A time period was requested but no joined date/time column is available.")
        start, end = bounds
        date_expr = column_expr(time_table, time_column)
        where_parts.append(f"{date_expr} >= {_quote_literal(start)}")
        where_parts.append(f"{date_expr} < {_quote_literal(end)}")

    from_sql = f"{q(base_table)} AS {q(aliases[base_table])}" if joins_sql else q(base_table)
    if joins_sql:
        from_sql += " " + " ".join(joins_sql)
    where_sql = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    limit = query_plan.limit
    if chart_type == "histogram":
        if not metric:
            raise ValueError("A histogram needs a numeric metric column.")
        select_expr = column_expr(metric_table, metric)
        select_value = f"{select_expr} AS {q(metric)}" if len(aliases) > 1 else select_expr
        sql = f"SELECT {select_value} FROM {from_sql}{where_sql}"
        limit = limit or min(MAX_RESULT_ROWS, 2000)
    elif metric is None or query_plan.aggregation == "NONE":
        # Row inspection is always scoped to the explicitly selected table.
        sql = f"SELECT * FROM {q(base_table)}{where_sql}"
        limit = limit or 10
    else:
        if not metric:
            raise ValueError("A metric is required for this query.")
        metric_expr = column_expr(metric_table, metric)
        agg = (query_plan.aggregation or "SUM").upper()
        if agg not in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
            raise ValueError(f"Unsupported aggregation: {agg}")
        alias = f"{agg.lower()}_{re.sub(r'[^A-Za-z0-9_]', '_', metric)}" if agg != "SUM" else f"total_{re.sub(r'[^A-Za-z0-9_]', '_', metric)}"
        metric_select = f"{agg}({metric_expr}) AS {q(alias)}"
        if dimension:
            dimension_expr = column_expr(dimension_table, dimension)
            select_dimension = f"{dimension_expr} AS {q(dimension)}"
            sql = f"SELECT {select_dimension}, {metric_select} FROM {from_sql}{where_sql} GROUP BY {dimension_expr}"
            if chart_type == "line":
                sql += f" ORDER BY {dimension_expr} ASC"
            elif query_plan.sort_order in {"ascending", "descending"}:
                direction = "ASC" if query_plan.sort_order == "ascending" else "DESC"
                sql += f" ORDER BY {q(alias)} {direction}"
            if query_plan.sort_order in {"ascending", "descending"}:
                limit = limit or 1
            elif limit is None:
                limit = min(MAX_RESULT_ROWS, 500)
        else:
            sql = f"SELECT {metric_select} FROM {from_sql}{where_sql}"

    if limit is not None:
        limit = max(1, min(int(limit), MAX_RESULT_ROWS))
        sql += f" LIMIT {limit}"
    return sql + ";"


def generate_sql(query_plan, schema: dict, business_context: dict | None = None,
                 dialect: str = "SQLite", force_llm: bool = False) -> SQLResult:
    if not force_llm:
        try:
            return SQLResult(sql=build_sql_deterministically(query_plan, schema, dialect))
        except NotImplementedError:
            if not ENABLE_LLM_FALLBACK:
                raise
        except ValueError:
            raise
    if not ENABLE_LLM_FALLBACK or not GEMINI_API_KEY or genai is None or genai.Client is None:
        raise ValueError("This query needs LLM SQL generation, but Gemini fallback is not configured.")
    prompt = build_sql_prompt(query_plan, schema, business_context, dialect)
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": SQLResult},
    )
    if not response.text:
        raise RuntimeError("The LLM returned an empty SQL response.")
    return SQLResult.model_validate_json(response.text)
