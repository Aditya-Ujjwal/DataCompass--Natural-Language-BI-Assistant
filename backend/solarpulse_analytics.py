from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import re
from typing import Any

from intent import QueryIntent
from query_plan import QueryPlan
from visualization import VisualizationSpec
from config import MAX_RESULT_ROWS


def _norm(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _quote(value: str, dialect: str) -> str:
    quote = "`" if dialect.lower() in {"mysql", "mariadb"} else '"'
    return quote + value.replace(quote, quote + quote) + quote


def _column(schema: dict[str, Any], table: str, aliases: tuple[str, ...]) -> dict[str, Any] | None:
    wanted = {_norm(alias) for alias in aliases}
    for item in schema.get(table, []):
        if _norm(item.get("name", "")) in wanted:
            return item
    return None


def _tables_with(schema: dict[str, Any], required: tuple[str, ...], preferred: tuple[str, ...] = ()) -> list[tuple[int, str, dict[str, dict[str, Any]]]]:
    found = []
    for table, columns in schema.items():
        resolved = {}
        for semantic in required:
            aliases = _COLUMN_ALIASES.get(semantic, (semantic,))
            match = _column(schema, table, aliases)
            if not match:
                break
            resolved[semantic] = match
        else:
            tokens = _norm(table)
            score = sum(20 for token in preferred if _norm(token) in tokens)
            # Prefer physical fact/result tables over a pre-aggregated view when
            # the required raw measures are available in both.
            if tokens.startswith("vw") or "view" in tokens:
                score -= 4
            if tokens in {"performanceresults", "performanceresult"}:
                score += 60
            if tokens in {"generationraw", "generationdata"}:
                score += 60
            score += len(columns) / 1000
            found.append((score, table, resolved))
    return sorted(found, reverse=True, key=lambda x: x[0])


_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "site": ("SiteKey", "SiteID", "SiteId", "SolarSiteKey"),
    "timestamp": ("Timestamp", "DateTime", "Date", "GenerationDate", "ReadingTime"),
    "actual": ("ActualGeneration", "ActualSolarGeneration", "ActualEnergy", "ActualOutput"),
    "expected": ("ExpectedGeneration", "ExpectedSolarGeneration", "ExpectedEnergy", "ExpectedOutput"),
    "solar": ("SolarGeneration", "Generation", "GeneratedEnergy", "EnergyGeneration"),
    "energy_loss": ("EnergyLoss", "TotalEnergyLoss", "LostEnergy", "GenerationLoss"),
    "deviation": ("PerformanceDeviation", "AveragePerformanceDeviation", "Deviation"),
    "ratio": ("PerformanceRatio", "AveragePerformanceRatio", "PR", "PerformanceRate"),
    "status": ("PerformanceStatus", "Status", "PerformanceCategory"),
    "streak": ("UnderperformanceStreak", "ContinuousUnderperformanceStreak", "UnderperformanceDays"),
    "persistent": ("PersistentUnderperformance", "IsPersistentlyUnderperforming", "PersistentFlag"),
}


@dataclass
class SolarPulseQuery:
    intent: QueryIntent
    plan: QueryPlan
    sql: str
    answer_kind: str
    visualization: VisualizationSpec


def _schema_has_semantic(schema: dict[str, Any], semantic: str) -> bool:
    return bool(_tables_with(schema, (semantic,)))


def _site_column(schema: dict[str, Any], table: str) -> str | None:
    item = _column(schema, table, _COLUMN_ALIASES["site"])
    return str(item["name"]) if item else None


def _make_plan(
    *, intent_name: str, table: str, metric: str | None, metrics: list[str],
    site: str | None, aggregation: str, chart: str, limit: int | None,
    semantic_operation: str, sort_order: str = "none", filters: list[str] | None = None,
    time_column: str | None = None, dimension_table: str | None = None,
    joins: list[dict[str, str]] | None = None,
) -> tuple[QueryIntent, QueryPlan]:
    intent = QueryIntent(
        intent=intent_name,
        metric=metric,
        dimension=site,
        table=table,
        filters=filters or [],
        sort_order=sort_order,
        limit=limit,
        chart_type=chart,
    )
    plan = QueryPlan(
        goal=f"SolarPulse analysis: {semantic_operation}.",
        table=table,
        metric_column=metric,
        metric_columns=metrics,
        additional_metrics=metrics[1:],
        dimension_column=site,
        aggregation=aggregation,
        filters=filters or [],
        sort_order=sort_order,
        limit=limit,
        chart_type=chart,
        metric_table=table,
        dimension_table=dimension_table or table,
        joins=joins or [],
        time_column=time_column,
        time_table=table if time_column else None,
        semantic_operation=semantic_operation,
    )
    return intent, plan


def _relationship_path(start_table: str, target_table: str, relationships: list[dict[str, Any]]) -> list[dict[str, str]] | None:
    if start_table == target_table:
        return []
    graph: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for rel in relationships:
        left, right = rel.get("from_table"), rel.get("to_table")
        if not left or not right:
            continue
        forward = {"from_table": left, "from_column": rel["from_column"], "to_table": right, "to_column": rel["to_column"]}
        reverse = {"from_table": right, "from_column": rel["to_column"], "to_table": left, "to_column": rel["from_column"]}
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


def _resolve_site_group(
    schema: dict[str, Any],
    base_table: str,
    site_key: str,
    relationships: list[dict[str, Any]],
    question: str,
) -> tuple[str, str, list[dict[str, str]]]:
    """Use a related human-readable site label when it exists; otherwise SiteKey."""
    if re.search(r"\b(site\s*key|sitekey|site\s*id|siteid)\b", question.lower()):
        return base_table, site_key, []
    candidates = []
    label_aliases = ("SiteName", "SolarSiteName", "SiteLabel", "SiteTitle")
    for table, columns in schema.items():
        for column in columns:
            if _norm(column.get("name", "")) not in {_norm(x) for x in label_aliases}:
                continue
            path = _relationship_path(base_table, table, relationships)
            if path is not None:
                score = 100 - len(path) * 10
                if table == base_table:
                    score += 10
                candidates.append((score, table, str(column["name"]), path))
    if not candidates:
        return base_table, site_key, []
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, table, column, path = candidates[0]
    return table, column, path


def _sql_grouped(
    table: str,
    group_column: str,
    expressions: list[tuple[str, str]],
    dialect: str,
    where: str = "",
    order_by: str | None = None,
    limit: int | None = None,
    dimension_table: str | None = None,
    joins: list[dict[str, str]] | None = None,
) -> str:
    q = lambda x: _quote(x, dialect)
    joins = joins or []
    aliases = {table: "t0"}
    join_sql = []
    for edge in joins:
        source = edge["from_table"]
        target = edge["to_table"]
        if source not in aliases:
            raise ValueError(f"Incomplete site dimension join path at {source}.")
        if target in aliases:
            continue
        alias = f"t{len(aliases)}"
        aliases[target] = alias
        join_sql.append(
            f"JOIN {q(target)} AS {q(alias)} ON "
            f"{q(aliases[source])}.{q(edge['from_column'])} = {q(alias)}.{q(edge['to_column'])}"
        )
    dimension_table = dimension_table or table
    if dimension_table not in aliases:
        raise ValueError(f"Site label table '{dimension_table}' is not joined.")
    def base_column(name: str) -> str:
        return f"{q(aliases[table])}.{q(name)}" if joins else q(name)
    group_expr = f"{q(aliases[dimension_table])}.{q(group_column)}" if joins else q(group_column)
    select_parts = [group_expr + " AS " + q(group_column)]
    select_parts.extend(f"{expression} AS {q(alias)}" for expression, alias in expressions)
    from_sql = f"{q(table)} AS {q(aliases[table])}" if joins else q(table)
    if join_sql:
        from_sql += " " + " ".join(join_sql)
    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"
    if where:
        sql += " WHERE " + where
    sql += f" GROUP BY {group_expr}"
    if order_by:
        sql += " ORDER BY " + order_by
    if limit:
        sql += f" LIMIT {max(1, min(int(limit), MAX_RESULT_ROWS))}"
    return sql + ";"


def build_solarpulse_query(question: str, schema: dict[str, Any], dialect: str, relationships: list[dict[str, Any]] | None = None) -> SolarPulseQuery | None:
    """Recognize common SolarPulse questions and build SQL from live columns.

    The function never assumes a table or column exists: each template is used
    only after the required physical fields have been discovered in one table.
    If no safe match exists, the main assistant falls back to its generic planner.
    """
    qtext = " ".join(question.lower().split())
    q = lambda x: _quote(x, dialect)
    relationships = relationships or []

    # Explicit requests for the performance table should inspect the physical
    # performance-results table rather than an aggregated performance view.
    asks_performance_table_rows = (
        "performance table" in qtext
        and any(term in qtext for term in ("all rows", "all records", "show me", "give me", "rows", "records"))
        and "critical" not in qtext
    )
    if asks_performance_table_rows:
        table_candidates = []
        for table in schema:
            table_token = _norm(table)
            if "performance" in table_token:
                score = 100 if table_token in {"performanceresults", "performanceresult"} else 40
                if table_token.startswith("vw"):
                    score -= 30
                table_candidates.append((score, table))
        if table_candidates:
            table_candidates.sort(reverse=True)
            table = table_candidates[0][1]
            sql = f"SELECT * FROM {q(table)} LIMIT {MAX_RESULT_ROWS};"
            intent, plan = _make_plan(
                intent_name="lookup", table=table, metric=None, metrics=[],
                site=None, aggregation="NONE", chart="table", limit=MAX_RESULT_ROWS,
                semantic_operation="inspect rows from the physical performance table",
            )
            return SolarPulseQuery(
                intent, plan, sql, "performance_table_rows",
                VisualizationSpec(chart_type="table", title="Performance Table Records"),
            )

    # (1) Recent Critical records must be checked before generic row-lookup logic.
    critical_detail = (
        ("critical" in qtext or "status = critical" in qtext)
        and any(term in qtext for term in ("most recent", "recent", "records", "show me", "display", "rows"))
        and any(term in qtext for term in ("actual generation", "expected generation", "performance deviation", "energy loss", "site id"))
    )
    if critical_detail:
        matches = _tables_with(schema, ("status", "timestamp"), preferred=("performance_results", "performance"))
        for _score, table, resolved in matches:
            requested_semantics = ["site", "timestamp", "actual", "expected", "deviation", "energy_loss", "status"]
            columns = []
            for semantic in requested_semantics:
                item = resolved.get(semantic) or _column(schema, table, _COLUMN_ALIASES.get(semantic, (semantic,)))
                if item:
                    physical = str(item["name"])
                    label = "SiteID" if semantic == "site" else physical
                    if physical not in [x[0] for x in columns]:
                        columns.append((physical, label))
            status_col = str(resolved["status"]["name"])
            timestamp_col = str(resolved["timestamp"]["name"])
            select_sql = ", ".join(f"{q(col)} AS {q(label)}" for col, label in columns)
            sql = (
                f"SELECT {select_sql} FROM {q(table)} "
                f"WHERE {q(status_col)} = 'Critical' "
                f"ORDER BY {q(timestamp_col)} DESC LIMIT 10;"
            )
            intent, plan = _make_plan(
                intent_name="lookup", table=table, metric=None, metrics=[],
                site=None, aggregation="NONE", chart="table", limit=10,
                semantic_operation="latest critical performance records",
                filters=[f"{status_col}=Critical"],
            )
            return SolarPulseQuery(
                intent, plan, sql, "critical_records",
                VisualizationSpec(chart_type="table", title="Latest Critical Performance Records"),
            )

    # (2) Compare actual vs expected generation by site, or over time.
    asks_actual_expected = (
        ("actual" in qtext and "expected" in qtext)
        and any(term in qtext for term in ("compare", "versus", " vs ", "against", "difference", "each site", "by site", "per site", "over time", "trend"))
    )
    if asks_actual_expected:
        matches = _tables_with(schema, ("actual", "expected", "timestamp" if any(x in qtext for x in ("over time", "trend", "time")) else "site"), preferred=("performance_results", "performance"))
        if matches:
            _score, table, cols = matches[0]
            actual = str(cols["actual"]["name"])
            expected = str(cols["expected"]["name"])
            if any(term in qtext for term in ("over time", "trend", "time")):
                ts = str(cols["timestamp"]["name"])
                expressions = [(f"SUM({q(actual)})", "TotalActualGeneration"), (f"SUM({q(expected)})", "TotalExpectedGeneration")]
                sql = (
                    f"SELECT {q(ts)} AS {q(ts)}, "
                    f"{expressions[0][0]} AS {q(expressions[0][1])}, "
                    f"{expressions[1][0]} AS {q(expressions[1][1])} "
                    f"FROM {q(table)} GROUP BY {q(ts)} ORDER BY {q(ts)} ASC LIMIT 500;"
                )
                intent, plan = _make_plan(intent_name="trend", table=table, metric=actual, metrics=[actual, expected], site=ts, aggregation="SUM", chart="line", limit=500, semantic_operation="actual versus expected solar generation over time", time_column=ts)
                visual = VisualizationSpec(chart_type="line", x=ts, y="TotalActualGeneration", series=["TotalExpectedGeneration"], title="Actual vs Expected Solar Generation Over Time")
                return SolarPulseQuery(intent, plan, sql, "actual_vs_expected_trend", visual)
            site_key = str(cols["site"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            sql = _sql_grouped(
                table, site,
                [(f"SUM({q(actual)})", "TotalActualGeneration"), (f"SUM({q(expected)})", "TotalExpectedGeneration")],
                dialect,
                order_by=f"{q('TotalActualGeneration')} DESC",
                dimension_table=dimension_table,
                joins=site_joins,
            )
            intent, plan = _make_plan(intent_name="comparison", table=table, metric=actual, metrics=[actual, expected], site=site, aggregation="SUM", chart="bar", limit=None, semantic_operation="compare summed actual and expected generation for every site", sort_order="descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar", x=site, y="TotalActualGeneration", series=["TotalExpectedGeneration"], title="Actual vs Expected Generation by Site")
            return SolarPulseQuery(intent, plan, sql, "actual_vs_expected_by_site", visual)

    # (3) Energy loss must target EnergyLoss, never SolarGeneration.
    if "energy loss" in qtext or "lost energy" in qtext or "generation loss" in qtext:
        matches = _tables_with(schema, ("energy_loss", "site"), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            site_key, metric = str(cols["site"]["name"]), str(cols["energy_loss"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            limit = 10 if any(word in qtext for word in ("sites", "which sites", "highest", "top")) else 1
            sql = _sql_grouped(table, site, [(f"SUM({q(metric)})", "TotalEnergyLoss")], dialect, order_by=f"{q('TotalEnergyLoss')} DESC", limit=limit, dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="ranking", table=table, metric=metric, metrics=[metric], site=site, aggregation="SUM", chart="bar", limit=limit, semantic_operation="rank sites by total energy loss", sort_order="descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar", x=site, y="TotalEnergyLoss", title="Total Energy Loss by Site")
            return SolarPulseQuery(intent, plan, sql, "energy_loss_ranking", visual)

    # (4) Performance status counts: Normal / Warning / Critical is a categorical distribution.
    if ("normal" in qtext and "warning" in qtext and "critical" in qtext) or (
        "performance status" in qtext and any(term in qtext for term in ("how many", "count", "categories", "category", "records"))
    ):
        matches = _tables_with(schema, ("status",), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            status = str(cols["status"]["name"])
            sql = f"SELECT {q(status)} AS {q(status)}, COUNT(*) AS {q('RecordCount')} FROM {q(table)} GROUP BY {q(status)} ORDER BY CASE LOWER({q(status)}) WHEN 'normal' THEN 1 WHEN 'warning' THEN 2 WHEN 'critical' THEN 3 ELSE 4 END;"
            intent, plan = _make_plan(intent_name="aggregation", table=table, metric=None, metrics=[], site=status, aggregation="COUNT", chart="pie", limit=None, semantic_operation="count performance records by status")
            visual = VisualizationSpec(chart_type="pie", x=status, y="RecordCount", title="Performance Records by Status")
            return SolarPulseQuery(intent, plan, sql, "status_counts", visual)

    # (5) Longest underperformance streak must use MAX(UnderperformanceStreak).
    if "underperformance streak" in qtext or "underperforming streak" in qtext or "continuous underperformance" in qtext:
        matches = _tables_with(schema, ("streak", "site"), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            site_key, streak = str(cols["site"]["name"]), str(cols["streak"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            sql = _sql_grouped(table, site, [(f"MAX({q(streak)})", "LongestUnderperformanceStreak")], dialect, order_by=f"{q('LongestUnderperformanceStreak')} DESC", limit=1, dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="ranking", table=table, metric=streak, metrics=[streak], site=site, aggregation="MAX", chart="kpi", limit=1, semantic_operation="find the maximum continuous underperformance streak by site", sort_order="descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="kpi", x=site, y="LongestUnderperformanceStreak", title="Longest Underperformance Streak")
            return SolarPulseQuery(intent, plan, sql, "longest_streak", visual)

    # (6) Persistent underperformance counts per site.
    if "persistent" in qtext and ("underperform" in qtext or "underperformance" in qtext):
        matches = _tables_with(schema, ("persistent", "site"), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            site_key, flag = str(cols["site"]["name"]), str(cols["persistent"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            dtype = str(cols["persistent"].get("type", "")).lower()
            if any(token in dtype for token in ("bool",)):
                predicate = f"{q(flag)} = TRUE"
            elif any(token in dtype for token in ("int", "number", "bit")):
                predicate = f"{q(flag)} = 1"
            else:
                cast_type = "CHAR" if dialect.lower() in {"mysql", "mariadb"} else "VARCHAR(10)"
                predicate = f"LOWER(CAST({q(flag)} AS {cast_type})) IN ('true', '1', 'yes', 'y')"
            sql = _sql_grouped(table, site, [("COUNT(*)", "PersistentUnderperformanceRecords")], dialect, where=predicate, order_by=f"{q('PersistentUnderperformanceRecords')} DESC", dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="aggregation", table=table, metric=flag, metrics=[flag], site=site, aggregation="COUNT", chart="bar", limit=None, semantic_operation="count persistent underperformance records per site", sort_order="descending", filters=[f"{flag}=true"], dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar", x=site, y="PersistentUnderperformanceRecords", title="Persistently Underperforming Records by Site")
            return SolarPulseQuery(intent, plan, sql, "persistent_counts", visual)

    # (7) Average performance deviation by site; negative values represent underperformance.
    if "performance deviation" in qtext or "deviation" in qtext and "performance" in qtext:
        matches = _tables_with(schema, ("deviation", "site"), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            site_key, metric = str(cols["site"]["name"]), str(cols["deviation"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            sort = "ASC" if any(term in qtext for term in ("worst", "lowest", "most negative", "underperform")) else "DESC"
            sql = _sql_grouped(table, site, [(f"AVG({q(metric)})", "AveragePerformanceDeviation")], dialect, order_by=f"{q('AveragePerformanceDeviation')} {sort}", dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="comparison", table=table, metric=metric, metrics=[metric], site=site, aggregation="AVG", chart="bar", limit=None, semantic_operation="calculate average performance deviation for every site and rank the worst deviation first", sort_order="ascending" if sort == "ASC" else "descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar", x=site, y="AveragePerformanceDeviation", title="Average Performance Deviation by Site")
            return SolarPulseQuery(intent, plan, sql, "deviation_by_site", visual)

    # (8) Average performance ratio across all sites, best first; do not LIMIT 1 when user asks to compare all.
    if "performance ratio" in qtext or "performance rate" in qtext:
        matches = _tables_with(schema, ("ratio", "site"), preferred=("performance_results", "performance"))
        if matches:
            _, table, cols = matches[0]
            site_key, metric = str(cols["site"]["name"]), str(cols["ratio"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            sql = _sql_grouped(table, site, [(f"AVG({q(metric)})", "AveragePerformanceRatio")], dialect, order_by=f"{q('AveragePerformanceRatio')} DESC", dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="comparison", table=table, metric=metric, metrics=[metric], site=site, aggregation="AVG", chart="bar", limit=None, semantic_operation="compare average performance ratio across all sites, best first", sort_order="descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar", x=site, y="AveragePerformanceRatio", title="Average Performance Ratio by Site")
            return SolarPulseQuery(intent, plan, sql, "ratio_by_site", visual)

    # (9) Solar generation trend over time.
    asks_solar_trend = (
        ("solar generation" in qtext or "solar energy" in qtext or "energy generated" in qtext or "generation" in qtext)
        and any(term in qtext for term in ("over time", "trend", "line chart", "line graph", "by date", "daily", "monthly"))
    )
    if asks_solar_trend:
        matches = _tables_with(schema, ("solar", "timestamp"), preferred=("generation_raw", "generation"))
        if matches:
            _, table, cols = matches[0]
            metric, timestamp = str(cols["solar"]["name"]), str(cols["timestamp"]["name"])
            sql = f"SELECT {q(timestamp)} AS {q(timestamp)}, SUM({q(metric)}) AS {q('TotalSolarGeneration')} FROM {q(table)} GROUP BY {q(timestamp)} ORDER BY {q(timestamp)} ASC LIMIT 500;"
            intent, plan = _make_plan(intent_name="trend", table=table, metric=metric, metrics=[metric], site=timestamp, aggregation="SUM", chart="line", limit=500, semantic_operation="trend of solar generation over time", sort_order="ascending", time_column=timestamp)
            visual = VisualizationSpec(chart_type="line", x=timestamp, y="TotalSolarGeneration", title="Solar Generation Over Time")
            return SolarPulseQuery(intent, plan, sql, "solar_generation_trend", visual)

    # (10) Site-wise total solar generation.
    if "solar generation" in qtext or "solar energy" in qtext or "energy generated" in qtext:
        matches = _tables_with(schema, ("solar", "site"), preferred=("generation_raw", "generation"))
        if matches:
            _, table, cols = matches[0]
            site_key, metric = str(cols["site"]["name"]), str(cols["solar"]["name"])
            dimension_table, site, site_joins = _resolve_site_group(schema, table, site_key, relationships, question)
            limit = 10 if any(word in qtext for word in ("sites", "which sites", "top")) else 1
            sql = _sql_grouped(table, site, [(f"SUM({q(metric)})", "TotalSolarGeneration")], dialect, order_by=f"{q('TotalSolarGeneration')} DESC", limit=limit, dimension_table=dimension_table, joins=site_joins)
            intent, plan = _make_plan(intent_name="ranking", table=table, metric=metric, metrics=[metric], site=site, aggregation="SUM", chart="bar" if limit > 1 else "kpi", limit=limit, semantic_operation="rank sites by total solar generation", sort_order="descending", dimension_table=dimension_table, joins=site_joins)
            visual = VisualizationSpec(chart_type="bar" if limit > 1 else "kpi", x=site, y="TotalSolarGeneration", title="Total Solar Generation by Site")
            return SolarPulseQuery(intent, plan, sql, "solar_generation_ranking", visual)

    return None


def build_solarpulse_answer(kind: str, execution: dict[str, Any]) -> str:
    columns = execution.get("columns", [])
    rows = execution.get("rows", [])
    if not rows:
        return "No matching SolarPulse records were found for the requested criteria."
    positions = {name: index for index, name in enumerate(columns)}
    def val(row, name):
        return row[positions[name]] if name in positions else None
    def fmt(value):
        if isinstance(value, (int, float)):
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        return str(value)
    if kind in {"actual_vs_expected_by_site", "actual_vs_expected_trend"}:
        examples = []
        for row in rows[:4]:
            site_or_time = val(row, "SiteKey")
            if site_or_time is None:
                site_or_time = row[0]
            actual, expected = val(row, "TotalActualGeneration"), val(row, "TotalExpectedGeneration")
            examples.append(f"{site_or_time}: actual {fmt(actual)}, expected {fmt(expected)}")
        return "Compared actual and expected solar generation using the connected performance data. " + "; ".join(examples) + ("." if examples else "")
    if kind == "energy_loss_ranking":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the highest total energy loss at {fmt(val(first, 'TotalEnergyLoss'))}. The chart and table show the next ranked sites."
    if kind == "deviation_by_site":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the lowest (most negative) average performance deviation at {fmt(val(first, 'AveragePerformanceDeviation'))}. All sites are ranked from worst deviation upward."
    if kind == "status_counts":
        items = [f"{val(row, columns[0])}: {fmt(val(row, 'RecordCount'))}" for row in rows]
        return "Performance records by status: " + "; ".join(items) + "."
    if kind == "longest_streak":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the longest recorded continuous underperformance streak: {fmt(val(first, 'LongestUnderperformanceStreak'))}."
    if kind == "persistent_counts":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the highest number of persistently underperforming records ({fmt(val(first, 'PersistentUnderperformanceRecords'))}). The chart compares all sites with matching records."
    if kind == "ratio_by_site":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the highest average performance ratio at {fmt(val(first, 'AveragePerformanceRatio'))}. The chart ranks all sites from highest to lowest average ratio."
    if kind == "critical_records":
        return "The latest Critical performance records are shown below, ordered from most recent to oldest, with the requested generation and deviation fields where available."
    if kind == "performance_table_rows":
        return f"Returned {len(rows)} rows from the performance table. The selected records are shown below."
    if kind == "solar_generation_trend":
        first, last = rows[0], rows[-1]
        return (f"Solar generation is plotted over time across {len(rows)} returned time points. "
                f"The first point is {fmt(val(first, 'TotalSolarGeneration'))} and the latest point is {fmt(val(last, 'TotalSolarGeneration'))}.")
    if kind == "solar_generation_ranking":
        first = rows[0]
        return f"Site {val(first, columns[0])} has the highest total solar generation at {fmt(val(first, 'TotalSolarGeneration'))}. The chart compares the returned site ranking."
    return f"Returned {len(rows)} SolarPulse result rows."
