from __future__ import annotations

from collections import deque
from typing import Any
import re

from pydantic import BaseModel, Field

from intent import QueryIntent


class QueryPlan(BaseModel):
    goal: str
    table: str
    metric_column: str | None = None
    metric_columns: list[str] = Field(default_factory=list)
    additional_metrics: list[str] = Field(default_factory=list)
    dimension_column: str | None = None
    aggregation: str = "SUM"
    filters: list[str] = Field(default_factory=list)
    time_period: str | None = None
    sort_order: str = "none"
    limit: int | None = None
    chart_type: str | None = None
    metric_table: str | None = None
    dimension_table: str | None = None
    time_column: str | None = None
    time_table: str | None = None
    joins: list[dict[str, str]] = Field(default_factory=list)
    sort_column: str | None = None
    semantic_operation: str | None = None


def _tokens(value: str) -> set[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    parts = re.findall(r"[a-z0-9]+", value.lower())
    result = set()
    for part in parts:
        if part.endswith("ies") and len(part) > 4:
            part = part[:-3] + "y"
        elif part.endswith("s") and not part.endswith("ss") and len(part) > 3:
            part = part[:-1]
        result.add(part)
    return result


def _canonical(value: str) -> str:
    return "_".join(sorted(_tokens(value)))


def _is_numeric(column: dict[str, Any]) -> bool:
    dtype = str(column.get("type", "")).lower()
    name = str(column.get("name", "")).lower()
    if column.get("primary_key") or name.endswith(("_id", "_key", "id", "key")):
        return False
    return any(token in dtype for token in ("int", "float", "real", "numeric", "decimal", "double", "number"))


def _is_text(column: dict[str, Any]) -> bool:
    dtype = str(column.get("type", "")).lower()
    return any(token in dtype for token in ("text", "char", "string", "enum", "varchar", "clob"))


def _is_date(column: dict[str, Any]) -> bool:
    name = str(column.get("name", "")).lower()
    dtype = str(column.get("type", "")).lower()
    return any(token in dtype for token in ("date", "time")) or any(
        token in name for token in ("date", "time", "timestamp", "datetime")
    )


def _resolve_metric(schema: dict[str, list[dict[str, Any]]], requested: str | None) -> list[tuple[str, dict[str, Any]]]:
    if not requested:
        return []
    aliases = {
        "total revenue": "revenue", "sales revenue": "revenue", "revenues": "revenue",
        "total sales": "revenue", "solar energy": "solar generation", "energy generated": "generation",
    }
    requested = aliases.get(requested.strip().lower(), requested)
    requested_tokens = _tokens(requested)
    exact = []
    fuzzy = []
    for table, columns in schema.items():
        for column in columns:
            if not _is_numeric(column):
                continue
            col_tokens = _tokens(column["name"])
            if str(column["name"]).lower() == requested.lower() or col_tokens == requested_tokens:
                exact.append((table, column))
            elif requested_tokens and requested_tokens.issubset(col_tokens):
                fuzzy.append((table, column))
    return exact or fuzzy


def _resolve_dimension(schema: dict[str, list[dict[str, Any]]], requested: str | None) -> list[tuple[str, dict[str, Any]]]:
    if not requested:
        return []
    requested_tokens = _tokens(requested)
    candidates = []
    for table, columns in schema.items():
        for column in columns:
            if _is_date(column):
                continue
            name = str(column["name"])
            tokens = _tokens(name)
            if not tokens:
                continue
            is_key = name.lower().endswith(("_id", "_key", "id", "key"))
            if not (_is_text(column) or is_key):
                continue
            if name.lower() == requested.lower() or tokens == requested_tokens:
                score = 100
            elif requested_tokens and requested_tokens.issubset(tokens):
                score = 80
            elif requested_tokens & tokens:
                score = 30 + 4 * len(requested_tokens & tokens)
            else:
                continue
            if _is_text(column) and any(token in tokens for token in ("name", "label", "title")):
                score += 15
            if _is_text(column):
                score += 10
            if column.get("primary_key"):
                score -= 20
            candidates.append((score, table, column))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(table, column) for _, table, column in candidates]


def _resolve_time_dimension(
    schema: dict[str, list[dict[str, Any]]],
    preferred_table: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for table, columns in schema.items():
        for column in columns:
            if _is_date(column):
                score = 0
                name = str(column["name"]).lower()
                if "timestamp" in name or "datetime" in name:
                    score += 20
                if "date" in name:
                    score += 10
                if table == preferred_table:
                    score += 30
                found.append((score, table, column))
    found.sort(key=lambda item: item[0], reverse=True)
    return [(table, column) for _, table, column in found]


def _relationship_path(
    start_table: str,
    target_table: str,
    relationships: list[dict[str, Any]],
) -> list[dict[str, str]] | None:
    if start_table == target_table:
        return []
    graph: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for rel in relationships:
        left = rel.get("from_table")
        right = rel.get("to_table")
        if not left or not right:
            continue
        forward = {
            "from_table": left,
            "from_column": rel["from_column"],
            "to_table": right,
            "to_column": rel["to_column"],
        }
        reverse = {
            "from_table": right,
            "from_column": rel["to_column"],
            "to_table": left,
            "to_column": rel["from_column"],
        }
        graph.setdefault(left, []).append((right, forward))
        graph.setdefault(right, []).append((left, reverse))

    queue = deque([(start_table, [])])
    visited = {start_table}
    while queue:
        current, path = queue.popleft()
        for neighbor, edge in graph.get(current, []):
            if neighbor in visited:
                continue
            next_path = path + [edge]
            if neighbor == target_table:
                return next_path
            visited.add(neighbor)
            queue.append((neighbor, next_path))
    return None


def _choose_metric_table(
    matches: list[tuple[str, dict[str, Any]]],
    explicit_table: str | None,
    question: str,
    prefer_date: bool,
) -> tuple[str, dict[str, Any]] | None:
    if not matches:
        return None
    if explicit_table:
        exact = [item for item in matches if item[0] == explicit_table]
        if exact:
            return exact[0]
    q_tokens = _tokens(question)
    scored = []
    for table, column in matches:
        score = len(q_tokens & _tokens(table)) * 10
        table_tokens = _tokens(table)
        if table_tokens & {"fact", "raw", "generation", "performance", "transaction", "measurement", "result"}:
            score += 3
        if prefer_date:
            score += 5
        scored.append((score, table, column))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1], scored[0][2]


def _choose_lookup_table(schema: dict[str, list[dict[str, Any]]], explicit_table: str | None) -> str:
    if explicit_table and explicit_table in schema:
        return explicit_table
    if not schema:
        raise ValueError("No accessible tables were found in the connected database.")
    # Prefer data/fact tables over small dimensions when the user asks for rows
    # without naming a table. Do not assume the first table is the correct one.
    scored = []
    for table, columns in schema.items():
        numeric_count = sum(1 for col in columns if _is_numeric(col))
        date_count = sum(1 for col in columns if _is_date(col))
        text_count = sum(1 for col in columns if _is_text(col))
        tokens = _tokens(table)
        score = len(columns) + numeric_count * 3 + date_count * 3 + min(text_count, 4)
        if tokens & {"raw", "fact", "data", "generation", "performance", "sales", "transaction", "measurement"}:
            score += 12
        if tokens & {"detail", "details", "dimension", "lookup", "reference"}:
            score -= 4
        scored.append((score, table))
    scored.sort(reverse=True)
    return scored[0][1]



def _select_aggregation(intent: QueryIntent, metric_column: str, question: str) -> str:
    """Choose an aggregation that matches the business meaning of the measure."""
    if intent.intent == "lookup" or intent.chart_type == "histogram":
        return "NONE"
    question_lower = question.lower()
    if re.search(r"\b(average|avg|mean)\b", question_lower):
        return "AVG"
    if re.search(r"\b(count|number of)\b", question_lower):
        return "COUNT"
    if re.search(r"\b(maximum|max)\b", question_lower) and not intent.dimension:
        return "MAX"
    if re.search(r"\b(minimum|min)\b", question_lower) and not intent.dimension:
        return "MIN"
    measure_tokens = _tokens(metric_column)
    # Ratios, rates and scores should usually be compared by average rather
    # than summing repeated observations for a site/campus.
    if measure_tokens & {"ratio", "rate", "score", "efficiency", "percentage", "percent", "deviation", "index"}:
        return "AVG"
    return "SUM"

def create_query_plan(
    intent: QueryIntent,
    schema: dict[str, list[dict[str, Any]]],
    relationships: list[dict[str, Any]] | None = None,
    question: str = "",
) -> QueryPlan:
    """Build a query plan across all discovered tables, joining related dimensions when needed."""
    if intent.intent == "metadata":
        raise ValueError("Database catalog requests are handled by the database-profile endpoint.")
    if intent.intent == "unknown":
        raise ValueError(
            "I couldn't confidently map that question to the connected database. "
            "Open Database explorer to review available tables and columns, then ask using a metric or category from the catalog."
        )

    relationships = relationships or []
    explicit_table = intent.table if intent.table in schema else None

    if intent.intent == "lookup" and intent.metric is None:
        table = _choose_lookup_table(schema, explicit_table)
        return QueryPlan(
            goal=f"Show a limited set of rows from {table}.", table=table,
            aggregation="NONE", filters=intent.filters,
            time_period=intent.time_period, sort_order=intent.sort_order,
            limit=intent.limit or 10, chart_type="table",
        )

    if not schema:
        raise ValueError("No accessible tables were found in the connected database.")

    metric_matches = _resolve_metric(schema, intent.metric)
    chosen_metric = _choose_metric_table(
        metric_matches, explicit_table, question, bool(intent.time_period)
    )
    if chosen_metric is None:
        raise ValueError(
            f"Could not find numeric metric '{intent.metric}' in any discovered table. "
            "Open Database explorer to inspect the available numeric columns."
        )
    metric_table, metric_meta = chosen_metric
    metric_column = str(metric_meta["name"])

    dimension_matches = _resolve_dimension(schema, intent.dimension)
    if not dimension_matches and intent.dimension and intent.chart_type == "line":
        dimension_matches = _resolve_time_dimension(schema, metric_table)
    dimension_table: str | None = None
    dimension_column: str | None = None
    joins: list[dict[str, str]] = []
    if intent.dimension:
        reachable = []
        for candidate_table, candidate_column in dimension_matches:
            path = _relationship_path(metric_table, candidate_table, relationships)
            if path is not None:
                score = 0
                if _is_text(candidate_column):
                    score += 45
                if any(token in _tokens(candidate_column["name"]) for token in ("name", "label", "title")):
                    score += 35
                if candidate_table == metric_table:
                    score += 10
                score -= len(path)
                reachable.append((score, candidate_table, candidate_column, path))
        if not reachable:
            available = ", ".join(sorted(schema.keys()))
            raise ValueError(
                f"I found metric '{metric_column}', but couldn't find a related '{intent.dimension}' "
                f"dimension through the discovered table relationships. Available tables: {available}. "
                "Check that the database defines foreign keys or matching primary-key columns."
            )
        reachable.sort(key=lambda item: item[0], reverse=True)
        _, dimension_table, dimension_meta, joins = reachable[0]
        dimension_column = str(dimension_meta["name"])

    time_column: str | None = None
    time_table: str | None = None
    if intent.time_period or intent.chart_type == "line" and not dimension_column:
        time_matches = _resolve_time_dimension(schema, metric_table)
        for candidate_table, candidate_column in time_matches:
            path = _relationship_path(metric_table, candidate_table, relationships)
            if path is not None:
                time_table = candidate_table
                time_column = str(candidate_column["name"])
                if intent.chart_type == "line" and dimension_column is None:
                    dimension_table = candidate_table
                    dimension_column = time_column
                # A time filter may require a second related table in addition
                # to the category table already selected for the chart.
                known_destinations = {edge["to_table"] for edge in joins}
                for edge in path:
                    if edge["to_table"] not in known_destinations:
                        joins.append(edge)
                        known_destinations.add(edge["to_table"])
                break
        if intent.time_period and time_column is None:
            raise ValueError("A time filter was requested, but no date/time column was discovered in the connected database.")

    if intent.chart_type in {"bar", "pie"} and dimension_column is None:
        raise ValueError(f"A {intent.chart_type} chart needs a category. Ask for a chart by site, campus, city, product, or another discovered category.")
    if intent.chart_type == "line" and dimension_column is None:
        raise ValueError("A line chart needs a discovered date/time column or a category for its horizontal axis.")
    if intent.chart_type == "histogram" and not _is_numeric(metric_meta):
        raise ValueError(f"A histogram requires a numeric field. '{metric_column}' is not numeric.")

    aggregation = _select_aggregation(intent, metric_column, question)
    if intent.intent == "trend" and intent.chart_type is None:
        aggregation = "SUM"

    # Filters can refer to descriptive columns in another related table (for
    # example, SiteName='North Solar Park'). Include the FK path for those too.
    for filter_item in intent.filters or []:
        if "=" not in filter_item:
            continue
        filter_column = filter_item.split("=", 1)[0].strip()
        if "." not in filter_column:
            continue
        filter_table, physical_column = filter_column.rsplit(".", 1)
        if filter_table not in schema or physical_column not in {c["name"] for c in schema[filter_table]}:
            raise ValueError(f"Filter references an undiscovered column: {filter_column}")
        filter_path = _relationship_path(metric_table, filter_table, relationships)
        if filter_path is None:
            raise ValueError(f"Filter column '{filter_column}' is not related to the metric table '{metric_table}'.")
        known_destinations = {edge["to_table"] for edge in joins}
        for edge in filter_path:
            if edge["to_table"] not in known_destinations:
                joins.append(edge)
                known_destinations.add(edge["to_table"])

    # De-duplicate join path edges and retain path order from the metric table.
    deduped_joins: list[dict[str, str]] = []
    seen_join_tables = {metric_table}
    for edge in joins:
        if edge["to_table"] in seen_join_tables:
            continue
        deduped_joins.append(edge)
        seen_join_tables.add(edge["to_table"])

    return QueryPlan(
        goal=f"Answer the user's {intent.intent} question using {metric_table} and related dimensions.",
        table=metric_table,
        metric_column=metric_column,
        dimension_column=dimension_column,
        aggregation=aggregation,
        filters=intent.filters,
        time_period=intent.time_period,
        sort_order=intent.sort_order,
        limit=intent.limit,
        chart_type=intent.chart_type,
        metric_table=metric_table,
        dimension_table=dimension_table or metric_table,
        time_column=time_column,
        time_table=time_table,
        joins=deduped_joins,
    )


def print_query_plan(plan: QueryPlan) -> None:
    print("\nQuery plan:")
    for field, value in plan.model_dump().items():
        print(f"  {field.replace('_', ' ').title()}: {value}")
