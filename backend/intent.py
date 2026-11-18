from __future__ import annotations

from typing import Any, Literal
import re

from pydantic import BaseModel, Field

try:
    from google import genai
except ImportError:
    from types import SimpleNamespace
    genai = SimpleNamespace(Client=None)

from config import GEMINI_API_KEY, GEMINI_MODEL, ENABLE_LLM_FALLBACK, MAX_RESULT_ROWS


class QueryIntent(BaseModel):
    """Structured analytical request extracted from the user's wording."""

    intent: Literal[
        "lookup", "aggregation", "comparison", "ranking", "trend",
        "distribution", "metadata", "unknown",
    ]
    metric: str | None = None
    dimension: str | None = None
    table: str | None = None
    filters: list[str] = Field(default_factory=list)
    time_period: str | None = None
    sort_order: Literal["ascending", "descending", "none"] = "none"
    limit: int | None = None
    chart_type: Literal["bar", "line", "pie", "histogram", "table", "kpi"] | None = None


_METRIC_ALIASES = {
    "total revenue": "revenue", "sales revenue": "revenue", "revenues": "revenue",
    "total sales": "revenue", "sales amount": "revenue", "revenue": "revenue",
    "profits": "profit", "profit": "profit", "costs": "cost", "cost": "cost",
    "quantity": "quantity", "units sold": "quantity", "number of units": "quantity",
    "count": "count",
}
_DIMENSION_ALIASES = {
    "cities": "city", "city": "city", "citites": "city", "products": "product",
    "product": "product", "customers": "customer", "customer": "customer",
    "regions": "region", "region": "region", "categories": "category", "category": "category",
    "sites": "site", "site": "site", "solar sites": "site", "solar site": "site",
    "campuses": "campus", "campus": "campus", "plants": "plant", "plant": "plant",
}
# Domain language -> physical database concepts. Candidate matching still requires
# a real numeric column to exist in the connected schema.
_METRIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "solar energy": ("solar", "energy", "generation", "generated", "production", "output", "power"),
    "solar power": ("solar", "power", "generation", "generated", "production", "output"),
    "energy generated": ("energy", "generation", "generated", "production", "output"),
    "energy generation": ("energy", "generation", "generated", "production", "output"),
    "energy production": ("energy", "generation", "generated", "production", "output"),
    "energy generated": ("energy", "generation", "generated", "production", "output"),
    "energy": ("energy", "generation", "generated", "production", "output"),
    "solar output": ("solar", "energy", "generation", "output", "power"),
    "production": ("production", "generation", "output"),
    "generation": ("generation", "generated", "production", "output"),
    "generated energy": ("generated", "energy", "generation", "production"),
    "solar generation": ("solar", "generation", "generated", "production"),
    "power generated": ("power", "generated", "generation", "output"),
    "energy output": ("energy", "output", "generation", "production"),
    "performance ratio": ("performance", "ratio"),
    "performance score": ("performance", "score"),
    "performance deviation": ("performance", "deviation"),
    "performance": ("performance",),
    "revenue": ("revenue",),
    "profit": ("profit",),
    "cost": ("cost",),
    "quantity": ("quantity",),
}
_CHART_PATTERNS = [
    ("histogram", r"\b(histogram|frequency distribution|distribution histogram)\b"),
    ("line", r"\b(line chart|line graph|line plot|trend line|trend chart|line visualization)\b"),
    ("pie", r"\b(pie chart|pie graph|pie diagram|pie visualization|donut chart|doughnut chart)\b"),
    ("bar", r"\b(bar chart|bar graph|bar plot|bar visualization|column chart)\b"),
    ("table", r"\b(table view|show as table|tabular view)\b"),
]
_STOP_WORDS = {
    "which", "what", "who", "are", "is", "was", "were", "the", "a", "an", "of", "by",
    "for", "from", "in", "on", "to", "with", "me", "show", "give", "get", "all", "each",
    "every", "per", "and", "or", "that", "this", "these", "those", "highest", "lowest",
    "most", "least", "top", "bottom", "best", "worst", "generate", "make", "create", "plot",
    "chart", "graph", "visualize", "visualise", "please", "their", "has", "have", "had",
}


def _words(value: str) -> list[str]:
    """Split snake_case, PascalCase and regular text into comparable tokens."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    parts = re.findall(r"[a-z0-9]+", value.lower())
    output = []
    for part in parts:
        if part.endswith("ies") and len(part) > 4:
            part = part[:-3] + "y"
        elif part.endswith("s") and not part.endswith("ss") and len(part) > 3:
            part = part[:-1]
        output.append(part)
    return output


def _canonical_column(name: str) -> str:
    return "_".join(_words(name))


def _all_columns(schema: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    return [(table, column) for table, columns in (schema or {}).items() for column in columns]


def _is_numeric_type(value: Any) -> bool:
    dtype = str(value or "").lower()
    return any(token in dtype for token in (
        "int", "float", "real", "numeric", "decimal", "double", "number", "serial",
    ))


def _is_date_column(name: str, dtype: Any) -> bool:
    lower_name = name.lower()
    lower_type = str(dtype or "").lower()
    return (
        any(token in lower_type for token in ("date", "time"))
        or bool(re.search(r"(^|_)(date|time|timestamp|datetime)(_|$)", lower_name))
        or any(token in lower_name for token in ("timestamp", "datetime"))
    )


def _metric_column_candidates(schema: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    candidates = []
    for table, column in _all_columns(schema):
        name = str(column.get("name", ""))
        tokens = _words(name)
        if not _is_numeric_type(column.get("type")):
            continue
        if column.get("primary_key") or any(token in {"id", "key", "index"} for token in tokens):
            continue
        if _is_date_column(name, column.get("type")):
            continue
        candidates.append((table, column))
    return candidates


def _score_metric(question: str, table: str, column: dict[str, Any]) -> int:
    q = " ".join(_words(question))
    column_name = str(column["name"])
    col_tokens = set(_words(column_name))
    table_tokens = set(_words(table))
    score = 0

    # Explicit semantic concepts, for example "solar energy" -> SolarGeneration.
    for phrase, concept_tokens in sorted(_METRIC_CONCEPTS.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in q:
            overlap = len(set(concept_tokens) & col_tokens)
            if overlap:
                score = max(score, 20 + overlap * 12)
                if phrase == "performance" and "ratio" in col_tokens:
                    score += 3
                if phrase == "solar energy" and "solar" in col_tokens and "generation" in col_tokens:
                    score += 8

    q_tokens = set(_words(question)) - _STOP_WORDS
    overlap = q_tokens & col_tokens
    score = max(score, len(overlap) * 10)
    if "energy" in q_tokens and "generation" in col_tokens:
        score += 8
    if "solar" in q_tokens and "solar" in col_tokens:
        score += 4
    if "performance" in q_tokens and "performance" in col_tokens:
        score += 8
    if "ratio" in q_tokens and "ratio" in col_tokens:
        score += 5
    if "generation" in q_tokens and "generation" in col_tokens:
        score += 6
    if table_tokens & q_tokens:
        score += 2
    return score


def _normalise_metric(question: str, schema: dict[str, Any] | None = None) -> str | None:
    q = question.lower()
    if schema is None:
        for phrase in sorted(_METRIC_ALIASES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(phrase)}\b", q):
                return _METRIC_ALIASES[phrase]
        return None

    candidates = _metric_column_candidates(schema)
    if not candidates:
        return None

    # Preserve explicit common business metric names when that exact column exists.
    for phrase in sorted(_METRIC_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", q):
            canonical = _canonical_column(_METRIC_ALIASES[phrase])
            exact = [(t, c) for t, c in candidates if _canonical_column(c["name"]) == canonical]
            if exact:
                return exact[0][1]["name"]

    candidate_counts: dict[str, int] = {}
    for candidate_table, _column in candidates:
        candidate_counts[candidate_table] = candidate_counts.get(candidate_table, 0) + 1

    scored = []
    question_tokens = set(_words(question)) - _STOP_WORDS
    for table, column in candidates:
        score = _score_metric(question, table, column)
        table_tokens = set(_words(table))
        # Some warehouse tables use generic numeric names such as Value or
        # Reading. If the question clearly names the fact table's subject and
        # that table has exactly one eligible numeric measure, use it. If it
        # has several measures, keep the request ambiguous instead of guessing.
        if score < 18 and candidate_counts.get(table) == 1:
            semantic_table_terms = table_tokens & question_tokens
            if semantic_table_terms and semantic_table_terms - {"raw", "data", "fact", "result"}:
                score = 18
        scored.append((score, table, column))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        return None
    # Avoid arbitrary selection when several metrics tie with a weak lexical match.
    if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][0] < 18:
        return None
    return str(scored[0][2]["name"])


def _dimension_candidates(schema: dict[str, Any] | None) -> list[tuple[str, dict[str, Any], int]]:
    result = []
    for table, column in _all_columns(schema):
        name = str(column.get("name", ""))
        tokens = _words(name)
        dtype = str(column.get("type", "")).lower()
        if _is_date_column(name, dtype):
            continue
        is_text = any(token in dtype for token in ("text", "char", "string", "enum", "varchar", "clob"))
        is_key = name.lower().endswith(("id", "key", "_id", "_key"))
        if is_text:
            priority = 4 if any(token in tokens for token in ("name", "label", "title", "description")) else 3
        elif is_key and not column.get("primary_key"):
            priority = 1
        elif is_key and column.get("primary_key"):
            priority = 0
        else:
            continue
        if name.lower() in {"id", "key", "createdby", "updatedby"}:
            continue
        result.append((table, column, priority))
    return result


def _normalise_dimension(question: str, schema: dict[str, Any] | None = None) -> str | None:
    lower = question.lower()
    if schema is None:
        for phrase in sorted(_DIMENSION_ALIASES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(phrase)}\b", lower):
                return _DIMENSION_ALIASES[phrase]
        return None

    desired: str | None = None
    for phrase in sorted(_DIMENSION_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            desired = _DIMENSION_ALIASES[phrase]
            break

    candidates = _dimension_candidates(schema)
    if desired:
        matching = []
        for table, column, priority in candidates:
            tokens = set(_words(column["name"]))
            table_tokens = set(_words(table))
            if desired in tokens:
                score = 20 + priority * 3
                if "name" in tokens or "label" in tokens:
                    score += 8
                if desired in table_tokens:
                    score += 2
                matching.append((score, column["name"]))
        if matching:
            matching.sort(reverse=True)
            return str(matching[0][1])

    q_tokens = set(_words(question)) - _STOP_WORDS
    scored = []
    for table, column, priority in candidates:
        tokens = set(_words(column["name"]))
        overlap = tokens & q_tokens
        if not overlap:
            continue
        score = len(overlap) * 10 + priority * 2
        if "name" in tokens or "label" in tokens:
            score += 4
        scored.append((score, column["name"]))
    if scored:
        scored.sort(reverse=True)
        return str(scored[0][1])
    return None


def _extract_limit(question: str) -> int | None:
    patterns = [
        r"\b(?:top|bottom|first|last)\s+(\d+)\b",
        r"\b(\d+)\s+(?:rows?|records?|cities|sites|campuses|products|customers|orders)\b",
        r"\bshow\s+(?:me\s+)?(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return max(1, min(int(match.group(1)), 5000))
    return None


def _find_date_dimension(schema: dict[str, Any] | None) -> str | None:
    date_columns = [
        (table, column) for table, column in _all_columns(schema)
        if _is_date_column(str(column.get("name", "")), column.get("type"))
    ]
    if not date_columns:
        return None
    # Prefer timestamp/date names over generic year/month fields.
    date_columns.sort(key=lambda item: (
        0 if "timestamp" in str(item[1]["name"]).lower() else 1,
        0 if "date" in str(item[1]["name"]).lower() else 1,
    ))
    return str(date_columns[0][1]["name"])


def _find_explicit_table(question: str, schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    q_tokens = set(_words(question))
    has_table_reference = bool(re.search(r"\b(table|view|from|within)\b", question, re.IGNORECASE))
    matches = []
    for table in schema:
        table_tokens = set(_words(table))
        if not table_tokens:
            continue
        if table_tokens.issubset(q_tokens):
            matches.append((len(table_tokens) + 10, table))
        elif has_table_reference and any(token in q_tokens for token in table_tokens if len(token) > 4):
            matches.append((1, table))
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return None


def _asks_for_catalog(question: str) -> bool:
    q = question.lower()
    catalog_phrases = (
        "all tables", "list tables", "show tables", "what tables", "which tables",
        "database schema", "show schema", "read all the tables", "read all tables",
        "database structure", "table structure", "available tables", "database catalog",
        "describe database", "describe the database", "table list", "all database tables",
    )
    return any(phrase in q for phrase in catalog_phrases)


def parse_question_rules(
    question: str,
    schema: dict[str, Any] | None = None,
    known_values: dict[str, list[str]] | None = None,
) -> QueryIntent | None:
    """Parse common database questions locally using the live discovered schema."""
    q = " ".join(question.lower().strip().split())
    if not q:
        return None

    if _asks_for_catalog(q):
        return QueryIntent(intent="metadata", metric=None, dimension=None, chart_type="table")

    chart_type = None
    for chart, pattern in _CHART_PATTERNS:
        if re.search(pattern, q):
            chart_type = chart
            break

    limit = _extract_limit(q)
    explicit_table = _find_explicit_table(q, schema)
    is_row_request = bool(re.search(
        r"\b(rows?|records?|dataset|raw data|show (?:me )?data|list all data|all records|all rows)\b", q
    )) and chart_type != "histogram"
    if is_row_request:
        asks_all_rows = bool(re.search(r"\b(all|every)\s+(rows?|records?)\b", q))
        return QueryIntent(
            intent="lookup", metric=None, dimension=None, table=explicit_table,
            limit=limit or (MAX_RESULT_ROWS if asks_all_rows else 10), chart_type="table",
        )

    metric = _normalise_metric(q, schema=schema)
    dimension = _normalise_dimension(q, schema=schema)
    if chart_type == "line" and dimension is None:
        dimension = _find_date_dimension(schema)
    if chart_type is None and re.search(r"\b(over time|trend|by date|monthly|weekly|daily|over the year)\b", q):
        chart_type = "line"
        dimension = dimension or _find_date_dimension(schema)

    if metric is None:
        # A chart type is not sufficient to identify which metric to plot.
        return None

    descending = bool(re.search(r"\b(highest|largest|most|top|max|maximum|best)\b", q))
    ascending = bool(re.search(r"\b(lowest|smallest|least|bottom|min|minimum|worst)\b", q))
    is_ranking = descending or ascending

    if chart_type == "histogram":
        intent_type = "distribution"
        dimension = None
        sort_order = "none"
    elif is_ranking:
        intent_type = "ranking"
        sort_order = "descending" if descending else "ascending"
        if limit is None:
            limit = 1
    elif chart_type or (dimension and re.search(
        r"\b(compare|versus|vs\.?|each|per|by|chart|graph|plot|share|distribution)\b", q
    )):
        intent_type = "comparison" if chart_type in {"bar", "pie"} or re.search(r"\b(compare|versus|vs\.?|chart|graph|plot)\b", q) else "aggregation"
        sort_order = "none"
    else:
        intent_type = "aggregation"
        sort_order = "none"

    time_period = None
    time_aliases = [
        "last quarter", "previous quarter", "this quarter", "last month", "previous month",
        "this month", "last year", "previous year", "this year", "last 30 days", "last 7 days",
    ]
    for phrase in time_aliases:
        if phrase in q:
            time_period = phrase
            break

    filters: list[str] = []
    if known_values and not (dimension and re.search(r"\b(by|each|per|top|bottom|highest|lowest)\b", q)):
        for qualified_column, values in known_values.items():
            for value in values:
                if value and re.search(rf"(?<!\w){re.escape(str(value).lower())}(?!\w)", q):
                    filters.append(f"{qualified_column}={value}")
                    break
            if filters:
                break

    return QueryIntent(
        intent=intent_type, metric=metric, dimension=dimension, table=explicit_table,
        filters=filters, time_period=time_period, sort_order=sort_order,
        limit=limit, chart_type=chart_type,
    )


def normalize_intent(intent: QueryIntent) -> QueryIntent:
    if intent.metric:
        intent.metric = _METRIC_ALIASES.get(intent.metric.strip().lower(), intent.metric.strip())
    if intent.dimension:
        intent.dimension = _DIMENSION_ALIASES.get(intent.dimension.strip().lower(), intent.dimension.strip())
    return intent


def understand_question(
    question: str,
    schema: dict[str, Any] | None = None,
    known_values: dict[str, list[str]] | None = None,
    force_llm: bool = False,
) -> QueryIntent:
    rule_result = parse_question_rules(question, schema=schema, known_values=known_values)
    if rule_result is not None and not force_llm:
        return rule_result

    if ((not ENABLE_LLM_FALLBACK and not force_llm) or not GEMINI_API_KEY
            or genai is None or genai.Client is None):
        return QueryIntent(intent="unknown", metric=None, dimension=None)

    schema_text = ""
    if schema:
        schema_text = "\nDISCOVERED DATABASE CATALOG\n" + "\n".join(
            f"{table}: " + ", ".join(
                f"{column['name']} ({column.get('type', 'unknown')})" for column in columns
            )
            for table, columns in schema.items()
        )
    prompt = f"""
You are a business intelligence query-understanding assistant.
Convert the question into the provided JSON schema. Do not answer and do not write SQL.
Use exact table/column names from the discovered schema. Use the entire catalog, not only
its first table. Distinguish row lookup, metric aggregation, ranking and chart requests.
If a measure and category are in related tables, return their physical column names.
Recognize business-language synonyms such as solar energy/solar generation and site/campus.
{schema_text}
QUESTION: {question}
""".strip()
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": QueryIntent},
    )
    if not response.text:
        raise RuntimeError("The LLM returned an empty intent response.")
    return normalize_intent(QueryIntent.model_validate_json(response.text))
